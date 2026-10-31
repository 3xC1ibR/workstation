#!/usr/bin/env python3
"""Archive inactive directories to S3 and retain local directory records.

Requires AWS CLI, bsdtar, and zstd. No AWS credentials are stored by this program.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import stat
import subprocess
import tarfile
import tempfile

RECORD_NAMES = {"ARCHIVE.md", "ARCHIVE.json", "FILE_INDEX.txt"}
DEFAULT_BUCKET = "walle-backups-392424878485-us-east-1"
STATE_ROOT = Path.home() / ".local/state/walle-archives"


def report(message):
    print(f"{datetime.now(timezone.utc).isoformat()} {message}", flush=True)


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def signature(metadata):
    return [metadata.st_dev, metadata.st_ino, metadata.st_mode,
            metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns]


def inventory(source, hash_contents=True):
    entries = {}
    for directory, directories, files in os.walk(source, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory) / name
            relative = path.relative_to(source).as_posix()
            metadata = path.lstat()
            entry = {"signature": signature(metadata), "mode": stat.S_IMODE(metadata.st_mode)}
            if stat.S_ISLNK(metadata.st_mode):
                entry.update(type="symlink", target=os.readlink(path))
                if name in directories:
                    directories.remove(name)
            elif stat.S_ISDIR(metadata.st_mode):
                entry.update(type="directory")
            elif stat.S_ISREG(metadata.st_mode):
                entry.update(type="file", size=metadata.st_size)
                if hash_contents:
                    entry["sha256"] = digest_file(path)
                    if signature(path.lstat()) != entry["signature"]:
                        raise RuntimeError(f"File changed during inventory: {path}")
            else:
                raise RuntimeError(f"Unsupported special file; stop its owner first: {path}")
            entries[relative] = entry
    return entries


def check_unchanged(source, entries, allow_removed=False):
    current = inventory(source, hash_contents=False)
    for name in RECORD_NAMES:
        current.pop(name, None)
    unexpected = set(current) - set(entries)
    if unexpected:
        raise RuntimeError(f"New source entries detected: {sorted(unexpected)[:5]}")
    removed_inodes = {tuple(entry["signature"][:2]) for name, entry in entries.items()
                      if allow_removed and name not in current and entry["type"] == "file"}
    for relative, original in entries.items():
        observed = current.get(relative)
        if observed is None:
            if allow_removed and original["type"] != "directory":
                continue
            raise RuntimeError(f"Source entry disappeared: {relative}")
        if original["type"] == "directory":
            # Creating records and evicting files changes directory timestamps.
            if observed["type"] != "directory" or observed["signature"][:3] != original["signature"][:3]:
                raise RuntimeError(f"Source directory changed: {relative}")
        elif observed["signature"] != original["signature"]:
            if not (tuple(original["signature"][:2]) in removed_inodes
                    and observed["signature"][:5] == original["signature"][:5]
                    and digest_file(source / relative) == original["sha256"]):
                raise RuntimeError(f"Source entry changed: {relative}")


def archive_member_name(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"Unsafe archive member: {value}")
    return str(path)


def verify_archive(archive, entries):
    """Read every archived file and compare its bytes with the original inventory."""
    seen = set()
    process = subprocess.Popen(["zstd", "-q", "-d", "-c", str(archive)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as members:
            for member in members:
                relative = archive_member_name(member.name)
                if relative == ".":
                    continue
                expected = entries.get(relative)
                if expected is None:
                    # bsdtar preserves macOS metadata through AppleDouble members.
                    if PurePosixPath(relative).name.startswith("._") and member.isfile():
                        continue
                    raise RuntimeError(f"Unexpected archived entry: {relative}")
                if relative in seen:
                    raise RuntimeError(f"Duplicate archived entry: {relative}")
                seen.add(relative)
                if expected["type"] == "directory":
                    valid = member.isdir()
                elif expected["type"] == "symlink":
                    valid = member.issym() and member.linkname == expected["target"]
                elif member.islnk():
                    linked = entries.get(archive_member_name(member.linkname), {})
                    valid = linked.get("sha256") == expected["sha256"]
                else:
                    valid = member.isfile() and member.size == expected["size"]
                    if valid:
                        content = members.extractfile(member)
                        digest = hashlib.sha256()
                        for block in iter(lambda: content.read(8 * 1024 * 1024), b""):
                            digest.update(block)
                        valid = digest.hexdigest() == expected["sha256"]
                if not valid:
                    raise RuntimeError(f"Archive content mismatch: {relative}")
        # Consume trailing padding so zstd can finish without SIGPIPE.
        for _ in iter(lambda: process.stdout.read(1024 * 1024), b""):
            pass
        if process.wait() != 0:
            raise RuntimeError("Archive decompression failed")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait()
    missing = set(entries) - seen
    if missing:
        raise RuntimeError(f"Archive is missing entries: {sorted(missing)[:5]}")


def run(arguments):
    subprocess.run([str(value) for value in arguments], check=True)


def aws_json(arguments):
    return json.loads(subprocess.check_output(["aws", *arguments, "--output", "json"], text=True))


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
    temporary.replace(path)


def download_verified(record, destination):
    run(["aws", "s3api", "get-object", "--bucket", record["bucket"],
         "--key", record["object_key"], "--version-id", record["version_id"],
         str(destination), "--query", "ContentLength", "--output", "text"])
    if destination.stat().st_size != record["archive_bytes"] or digest_file(destination) != record["archive_sha256"]:
        raise RuntimeError("Downloaded archive checksum mismatch; local contents must remain")


def write_records(source, record):
    write_json(source / "ARCHIVE.json", record)
    index = source / "FILE_INDEX.txt"
    with index.open("w") as stream:
        stream.write("type\tbytes\tpath (JSON encoded)\n")
        for relative, entry in sorted(record["entries"].items()):
            stream.write(f"{entry['type']}\t{entry.get('size', 0)}\t{json.dumps(relative)}\n")
    (source / "ARCHIVE.md").write_text(
        f"# Archived directory\n\n"
        f"Original directory: `{record['source']}`\n\n"
        f"Device: Walle. Snapshot: `{record['snapshot']}`.\n\n"
        f"Original file contents: {record['source_bytes'] / 1024**3:.3f} GiB.\n\n"
        f"Archive: `s3://{record['bucket']}/{record['object_key']}`\n\n"
        f"S3 version: `{record['version_id']}`\n\n"
        f"Archive SHA-256: `{record['archive_sha256']}`\n\n"
        "The directory tree and FILE_INDEX.txt remain locally. Payload files are stored in S3. "
        "ARCHIVE.json records whether local removal completed. Do not treat the empty directories as lost work.\n\n"
        "To restore to a new directory, first authenticate with `aws login`, then run:\n\n"
        "```sh\n"
        "python3 /opt/projects/workstation/scripts/archive_directory.py restore \\\n"
        f"  {shlex.quote(str(source))} \\\n"
        f"  --destination {shlex.quote(str(source.parent / (source.name + '-restored')))}\n"
        "```\n\n"
        "Restoration refuses an existing destination and checks all restored file contents. "
        "The archive contains hidden files, Git data, links, and filesystem metadata. "
        "Do not expire S3 objects or versions referenced by these records.\n"
    )


def evict(source, record):
    if record.get("verification") != "downloaded_sha256_and_all_file_contents":
        raise RuntimeError("Remote verification is required before local removal")
    check_unchanged(source, record["entries"], allow_removed=True)
    record["status"] = "removing_local_contents"
    write_records(source, record)
    removed_inodes = {tuple(entry["signature"][:2]) for name, entry in record["entries"].items()
                      if entry["type"] == "file" and not os.path.lexists(source / name)}
    for relative, entry in record["entries"].items():
        if entry["type"] == "directory":
            continue
        path = source / relative
        if not os.path.lexists(path):
            continue
        observed = signature(path.lstat())
        if observed != entry["signature"]:
            if not (tuple(entry["signature"][:2]) in removed_inodes
                    and observed[:5] == entry["signature"][:5]
                    and digest_file(path) == entry["sha256"]):
                raise RuntimeError(f"Source changed before removal: {relative}")
        path.unlink()
        if entry["type"] == "file":
            removed_inodes.add(tuple(entry["signature"][:2]))
    record["status"] = "archived"
    record["local_removal_completed_at"] = datetime.now(timezone.utc).isoformat()
    write_records(source, record)


def archive_directory(source, bucket, snapshot, remove_local):
    source = source.resolve(strict=True)
    if not source.is_dir() or source == Path("/"):
        raise RuntimeError("Source must be an ordinary project directory")
    if any((source / name).exists() for name in RECORD_NAMES):
        raise RuntimeError("Archive records already exist; use evict to resume verified removal")
    report(f"Inventory and hashes: {source}")
    entries = inventory(source)
    source_bytes = sum(entry.get("size", 0) for entry in entries.values())
    relative_source = source.relative_to("/").as_posix()
    state = STATE_ROOT / snapshot / relative_source
    state.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(state).free < source_bytes * 1.05 + 512 * 1024**2:
        raise RuntimeError("Insufficient staging space for this directory")
    write_json(state / "SOURCE_INVENTORY.json", entries)
    archive = state / "contents.tar.zst"
    if archive.exists():
        raise RuntimeError(f"Staged archive already exists: {archive}; inspect before retrying")
    report(f"Create archive: {len(entries)} entries, {source_bytes / 1024**3:.3f} GiB")
    run(["tar", "--format", "pax", "--acls", "--xattrs", "--zstd", "-cf", archive, "-C", source, "."])
    check_unchanged(source, entries)
    checksum = digest_file(archive)
    key = f"snapshots/{snapshot}/{relative_source}/contents.tar.zst"
    report(f"Upload: s3://{bucket}/{key} ({archive.stat().st_size / 1024**3:.3f} GiB)")
    run(["aws", "s3", "cp", archive, f"s3://{bucket}/{key}", "--only-show-errors",
         "--checksum-algorithm", "SHA256", "--metadata", f"sha256={checksum}"])
    remote = aws_json(["s3api", "head-object", "--bucket", bucket, "--key", key])
    if remote.get("ContentLength") != archive.stat().st_size or not remote.get("VersionId"):
        raise RuntimeError("Remote size or version verification failed")
    record = {
        "format_version": 1, "device": "walle", "source": str(source),
        "snapshot": snapshot, "bucket": bucket, "object_key": key,
        "version_id": remote["VersionId"], "source_bytes": source_bytes,
        "archive_bytes": archive.stat().st_size, "archive_sha256": checksum,
        "entries": entries, "status": "uploaded",
    }
    write_json(state / "ARCHIVE.json", record)
    # Reuse staging space: the source remains intact throughout remote verification.
    archive.unlink()
    report("Download exact S3 version and verify every archived file")
    download_verified(record, archive)
    verify_archive(archive, entries)
    check_unchanged(source, entries)
    record["verification"] = "downloaded_sha256_and_all_file_contents"
    record["verified_at"] = datetime.now(timezone.utc).isoformat()
    record["status"] = "verified_remote"
    write_json(state / "ARCHIVE.json", record)
    write_records(source, record)
    for name in RECORD_NAMES:
        run(["aws", "s3", "cp", source / name,
             f"s3://{bucket}/snapshots/{snapshot}/{relative_source}/{name}", "--only-show-errors"])
    if remove_local:
        report("Remote contents verified; removing local payload and retaining directory tree")
        evict(source, record)
        write_json(state / "ARCHIVE.json", record)
        run(["aws", "s3", "cp", source / "ARCHIVE.json",
             f"s3://{bucket}/snapshots/{snapshot}/{relative_source}/ARCHIVE.json", "--only-show-errors"])
    archive.unlink()
    report(f"Complete: {source} ({record['status']})")


def restore_directory(source, destination):
    record = json.loads((source / "ARCHIVE.json").read_text())
    destination = destination.absolute()
    if os.path.lexists(destination):
        raise RuntimeError("Restore destination must not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=STATE_ROOT) as staging:
        archive = Path(staging) / "contents.tar.zst"
        download_verified(record, archive)
        verify_archive(archive, record["entries"])
        destination.mkdir()
        run(["tar", "-xpf", archive, "-C", destination])
        restored = inventory(destination)
        if set(restored) != set(record["entries"]):
            raise RuntimeError("Restored directory inventory differs from the original")
        for relative, expected in record["entries"].items():
            actual = restored[relative]
            for field in ("type", "mode", "sha256", "size", "target"):
                if actual.get(field) != expected.get(field):
                    raise RuntimeError(f"Restored file mismatch: {relative} ({field})")
    report(f"Restored and verified: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("archive")
    create.add_argument("source", type=Path)
    create.add_argument("--bucket", default=DEFAULT_BUCKET)
    create.add_argument("--snapshot", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    create.add_argument("--remove-local", action="store_true")
    resume = commands.add_parser("evict")
    resume.add_argument("source", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "archive":
        if "/" in args.snapshot or args.snapshot in ("", ".", ".."):
            parser.error("Snapshot must be a single directory name")
        archive_directory(args.source, args.bucket, args.snapshot, args.remove_local)
    elif args.command == "evict":
        record = json.loads((args.source / "ARCHIVE.json").read_text())
        remote = aws_json(["s3api", "head-object", "--bucket", record["bucket"],
                           "--key", record["object_key"], "--version-id", record["version_id"]])
        if (remote["ContentLength"] != record["archive_bytes"]
                or remote.get("Metadata", {}).get("sha256") != record["archive_sha256"]):
            raise RuntimeError("Recorded remote archive no longer matches; local removal refused")
        evict(args.source, record)
        prefix = record["object_key"].rsplit("/", 1)[0]
        run(["aws", "s3", "cp", args.source / "ARCHIVE.json",
             f"s3://{record['bucket']}/{prefix}/ARCHIVE.json", "--only-show-errors"])
    else:
        restore_directory(args.source, args.destination)


if __name__ == "__main__":
    main()
