#!/usr/bin/env python3
"""Daily encrypted Restic backups, with online snapshots of native SQLite files."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

STATE = Path.home() / ".local/state/agent-data-backups"
REPOSITORY = "s3:s3.us-east-1.amazonaws.com/walle-backups-392424878485-us-east-1/agent-data/walle"
PASSWORD_SERVICE = "com.rquinonez.agent-data-backup.password"
CREDENTIAL_SERVICE = "com.rquinonez.agent-data-backup.aws"
RECOVERY_SECRET = "walle-backups/agent-data-restic-password"
IAM_USER = "walle-agent-data-backup"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def keychain(service, value=None):
    if value is None:
        result = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Missing Keychain item {service}; run --configure after AWS login")
        return result.stdout.strip()
    result = subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-a", "walle", "-s", service,
                             "-w", value], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Could not save Keychain item {service}")


def configure():
    """Provision local credentials after Terraform has created the scoped IAM user."""
    import secrets
    aws = ["/usr/local/bin/aws", "--region", "us-east-1", "--no-cli-pager"]
    identity = json.loads(subprocess.check_output(aws + ["sts", "get-caller-identity"]))
    if identity["Account"] != "392424878485":
        raise RuntimeError("AWS login is for a different account")
    try:
        local_password = keychain(PASSWORD_SERVICE)
    except RuntimeError:
        local_password = None
    result = subprocess.run(aws + ["secretsmanager", "get-secret-value", "--secret-id", RECOVERY_SECRET],
                            capture_output=True, text=True)
    if result.returncode:
        if "ResourceNotFoundException" not in result.stderr:
            raise RuntimeError("Could not read the Restic recovery secret")
        password = local_password or secrets.token_urlsafe(48)
        # AWS CLI on macOS rejects /dev/stdin here. The temporary file is 0600,
        # outside Git, removed on exit, and keeps the password out of arguments.
        with tempfile.NamedTemporaryFile(mode="w", prefix="recovery-", suffix=".json", dir=STATE) as request:
            json.dump({"SecretId": RECOVERY_SECRET, "SecretString": password}, request)
            request.flush()
            subprocess.run(aws + ["secretsmanager", "put-secret-value", "--cli-input-json", "file://" + request.name],
                           check=True, capture_output=True)
    else:
        password = json.loads(result.stdout)["SecretString"]
        if local_password and password != local_password:
            raise RuntimeError("Local and recovery passwords differ; review before replacing either")
    keychain(PASSWORD_SERVICE, password)
    try:
        json.loads(keychain(CREDENTIAL_SERVICE))
    except RuntimeError:
        keys = json.loads(subprocess.check_output(aws + ["iam", "list-access-keys", "--user-name", IAM_USER]))
        if keys["AccessKeyMetadata"]:
            raise RuntimeError("Backup IAM user already has a key but its Keychain item is missing; review before rotating")
        key = json.loads(subprocess.check_output(aws + ["iam", "create-access-key", "--user-name", IAM_USER]))["AccessKey"]
        try:
            keychain(CREDENTIAL_SERVICE, json.dumps({"access_key_id": key["AccessKeyId"],
                                                   "secret_access_key": key["SecretAccessKey"]}))
        except Exception:
            subprocess.run(aws + ["iam", "delete-access-key", "--user-name", IAM_USER,
                                  "--access-key-id", key["AccessKeyId"]], check=True, capture_output=True)
            raise
    # Initialization checks the bucket itself. Use the current administrator
    # login here so the daily identity can keep prefix-restricted ListBucket.
    administrator = json.loads(subprocess.check_output(aws + ["configure", "export-credentials", "--format", "process"]))
    environment = os.environ.copy()
    environment.update(RESTIC_REPOSITORY=REPOSITORY, RESTIC_PASSWORD=password,
                       AWS_ACCESS_KEY_ID=administrator["AccessKeyId"],
                       AWS_SECRET_ACCESS_KEY=administrator["SecretAccessKey"], AWS_DEFAULT_REGION="us-east-1")
    environment.pop("RESTIC_PASSWORD_FILE", None)
    environment.pop("AWS_SESSION_TOKEN", None)
    if administrator.get("SessionToken"):
        environment["AWS_SESSION_TOKEN"] = administrator["SessionToken"]
    probe = subprocess.run(["/opt/homebrew/bin/restic", "cat", "config"], env=environment, capture_output=True)
    if probe.returncode == 10:
        subprocess.run(["/opt/homebrew/bin/restic", "init"], env=environment, check=True)
    elif probe.returncode:
        raise RuntimeError(f"Could not initialize the encrypted repository (exit {probe.returncode})")
    print("Backup password and scoped AWS credentials are in Keychain; recovery password is in Secrets Manager.")


def default_roots():
    home = Path.home()
    roots = [home / name for name in [".codex", ".claude", ".claude.json", ".kimi-code", ".gemini",
             ".config/muse", ".local/share/muse", ".local/state/agent-coord", ".local/share/ribbon-field-browser"]]
    for variable in ["CODEX_HOME", "CLAUDE_CONFIG_DIR", "KIMI_CODE_HOME", "CLAUDE_CODE_TMPDIR"]:
        if os.environ.get(variable):
            roots.append(Path(os.environ[variable]).expanduser().absolute())
    if os.environ.get("XDG_DATA_HOME"):
        roots.append(Path(os.environ["XDG_DATA_HOME"]) / "muse")
    if os.environ.get("AGENT_COORD_DB"):
        roots.append(Path(os.environ["AGENT_COORD_DB"]).absolute())
    roots += [Path("/private/tmp") / f"claude-{os.getuid()}",
              Path(tempfile.gettempdir()) / f"claude-{os.getuid()}"]
    return list(dict.fromkeys(roots))


def regular_files(roots):
    for root in roots:
        if root.is_file() and not root.is_symlink():
            yield root
        elif root.is_dir() and not root.is_symlink():
            def fail(error):
                raise error
            for directory, _, files in os.walk(root, onerror=fail, followlinks=False):
                for name in files:
                    path = Path(directory) / name
                    try:
                        if stat.S_ISREG(path.lstat().st_mode):
                            yield path
                    except FileNotFoundError:
                        continue  # A concurrent process removed a temporary file.


def snapshot_database(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < source.stat().st_size + 512 * 1024 * 1024:
        raise RuntimeError(f"Insufficient disk space for SQLite staging: {source}")
    temporary = destination.with_name(destination.name + ".pending")
    for suffix in ["", "-wal", "-shm", "-journal"]:
        Path(str(temporary) + suffix).unlink(missing_ok=True)
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic() - started > 600:
            raise TimeoutError(f"SQLite snapshot exceeded ten minutes: {source}")
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as original:
            with closing(sqlite3.connect(temporary)) as target:
                original.backup(target, pages=-1, progress=progress)
                # The online backup API provides transaction consistency.
                # Read the resulting schema, but leave full B-tree audits to
                # restore verification rather than rereading gigabytes daily.
                target.execute("SELECT count(*) FROM sqlite_master").fetchone()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(roots, state):
    roots = list(dict.fromkeys(roots))
    roots = [path for path in roots if not any(path != parent and path.is_relative_to(parent)
             and parent.is_dir() and not parent.is_symlink() for parent in roots)]
    if any(state.is_relative_to(path) for path in roots):
        raise RuntimeError("Backup staging must be outside every source directory")
    (state / "sqlite").mkdir(parents=True, exist_ok=True)
    existing = [path for path in roots if path.exists()]
    manifest = {"started_at": timestamp(), "sources": [str(p) for p in existing],
                "missing_sources": [str(p) for p in roots if not p.exists()], "databases": []}
    exclusions = set()
    for path in regular_files(existing):
        try:
            with path.open("rb") as source:
                header = source.read(16)
        except FileNotFoundError:
            continue
        if header != b"SQLite format 3\x00":
            continue
        destination = state / "sqlite" / path.relative_to(path.anchor)
        print(f"{timestamp()} SQLite snapshot: {path}", flush=True)
        snapshot_database(path, destination)
        manifest["databases"].append({"source": str(path), "snapshot": str(destination)})
        exclusions.update(str(path) + suffix for suffix in ["", "-wal", "-shm", "-journal"])
    # Literal paths are escaped for Restic's glob matcher. No broad DB exclusions.
    escaped = []
    for path in sorted(exclusions):
        escaped.append("".join("\\" + char if char in "\\*?[]" else char for char in path))
    (state / "exclusions.txt").write_text("\n".join(escaped) + "\n")
    manifest["prepared_at"] = timestamp()
    save_json(state / "manifest.json", manifest)
    return existing, manifest


def restic_environment(config, state=STATE):
    environment = os.environ.copy()
    environment.update(RESTIC_REPOSITORY=config.get("repository", REPOSITORY),
                       RESTIC_CACHE_DIR=str(state / "cache"), AWS_DEFAULT_REGION="us-east-1",
                       AWS_EC2_METADATA_DISABLED="true")
    if config.get("password_file"):
        environment.pop("RESTIC_PASSWORD", None)
        environment["RESTIC_PASSWORD_FILE"] = config["password_file"]
    else:
        environment.pop("RESTIC_PASSWORD_FILE", None)
        environment["RESTIC_PASSWORD"] = keychain(PASSWORD_SERVICE)
    if environment["RESTIC_REPOSITORY"].startswith("s3:"):
        credentials = json.loads(keychain(CREDENTIAL_SERVICE))
        environment.update(AWS_ACCESS_KEY_ID=credentials["access_key_id"],
                           AWS_SECRET_ACCESS_KEY=credentials["secret_access_key"])
        for name in ["AWS_SESSION_TOKEN", "AWS_PROFILE", "AWS_DEFAULT_PROFILE"]:
            environment.pop(name, None)
    return environment


def run(config, state, prepare_only=False):
    roots = [Path(p).expanduser().absolute() for p in config.get("sources", [])] or default_roots()
    environment = None if prepare_only else restic_environment(config, state)
    roots, manifest = prepare(roots, state)
    if prepare_only:
        return manifest
    binary = config.get("restic", "/opt/homebrew/bin/restic")
    # Do not initialize on generic network/authentication failures. Exit 10 means no repository.
    probe = subprocess.run([binary, "cat", "config"], env=environment, capture_output=True)
    if probe.returncode == 10:
        subprocess.run([binary, "init"], env=environment, check=True)
    elif probe.returncode:
        raise RuntimeError(f"Restic repository could not be opened (exit {probe.returncode})")
    arguments = [binary, "backup", "--json", "--host", "walle", "--tag", "agent-data",
                 "--exclude-file", str(state / "exclusions.txt"), *map(str, roots),
                 str(state / "sqlite"), str(state / "manifest.json")]
    arguments += [str(path) for path in [state / "config.json", state / "configuration-backups"] if path.exists()]
    subprocess.run(arguments, env=environment, check=True)
    manifest["completed_at"] = timestamp()
    manifest["repository"] = environment["RESTIC_REPOSITORY"]
    # The encrypted snapshot now holds these copies. Keep local disk available.
    shutil.rmtree(state / "sqlite")
    return manifest


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--restic", nargs=argparse.REMAINDER, help="Run a Restic inspection or restore command")
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A backup is already running.")
            return 0
        if args.configure:
            configure()
            return 0
        config_path = args.state / "config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
        if args.restic:
            return subprocess.run([config.get("restic", "/opt/homebrew/bin/restic"), *args.restic],
                                  env=restic_environment(config, args.state)).returncode
        result = {"started_at": timestamp(), "status": "running"}
        save_json(args.state / "last-run.json", result)
        try:
            manifest = run(config, args.state, args.prepare_only)
            result.update(status="prepared" if args.prepare_only else "completed", finished_at=timestamp(),
                          databases=len(manifest["databases"]), sources=manifest["sources"])
        except Exception as error:
            result.update(status="failed", finished_at=timestamp(), error=str(error))
            print(f"Backup failed: {error}", file=sys.stderr)
            return 1
        finally:
            save_json(args.state / "last-run.json", result)
        return 0


if __name__ == "__main__":
    sys.exit(main())
