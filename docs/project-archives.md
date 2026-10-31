# Project archives on Walle

Walle keeps active projects on its local disk. Completed projects and inactive
data can be archived to S3. Their original directory trees remain locally so
the projects remain discoverable.

## Storage and ownership

- Bucket: `walle-backups-392424878485-us-east-1`.
- AWS account: `392424878485`; region: `us-east-1`.
- Terraform source: `/opt/projects/infra/walle-backups/terraform/`.
- Terraform state: the shared infrastructure state bucket, key
  `walle-backups/terraform.tfstate`.
- Object layout: `snapshots/<UTC timestamp>/opt/projects/<directory>/`.
- Each archived project has a `contents.tar.zst` object and archive records.
- The bucket blocks public access, requires HTTPS, uses SSE-S3 encryption, and
  enables versioning. Completed archives and their previous versions do not
  expire automatically. Incomplete multipart uploads expire after seven days.

Use the shared infrastructure Terraform root to change bucket configuration.
Do not use another project's deployment stack. Do not apply a retention policy
that deletes objects referenced by local archive records.

## Local records

Each archived project retains its directory tree and three files at its root:

- `ARCHIVE.md`: storage location, original size, and a restore command.
- `ARCHIVE.json`: the exact S3 object version, full archive SHA-256, original
  file hashes, links, metadata, and local removal status.
- `FILE_INDEX.txt`: a searchable inventory, including hidden files.

These records are pointers, not copies of the payload. Empty directories below
an archive record are intentional. Do not delete these records during routine
cleanup. Do not treat an empty `.git` directory within an archive as an active
repository. Restore the project before opening it as a working repository.

The first archival operation includes all projects in `/opt/projects/.archive`
and `/opt/projects/.dormant`. Tab Reader was moved from
`/opt/projects/tab_reader` to `/opt/projects/.archive/tab_reader` before archival.
The Kokoro model at
`/opt/projects/3rd-party/Kokoro-FastAPI/api/src/models/v1_0/kokoro-v1_0.pth`
was explicitly deleted rather than archived.

## Prerequisites

Install Python 3, the AWS CLI, macOS bsdtar, and zstd. Authenticate with
`aws login`, then verify the account with `aws sts get-caller-identity`.
Run the procedure only on inactive directories. Stop any program that writes
to the selected directory, including database processes and background agents.
Keep at least one directory's uncompressed file size plus 512 MiB available for
staging. Restoration also needs space for the restored contents.

The tool preserves all contents, including hidden files, Git history, links,
permissions, and macOS metadata. It does not silently exclude dependencies or
credentials. The archive destination is private. Maintain an independent backup
for irreplaceable contents; local pointers do not provide a second data copy.

## Archive a directory

Obtain user authorization for the selected directory and local removal. A
general disk-usage investigation does not authorize deletion. Choose one
inactive project at a time; do not archive a parent containing existing archive
records as a substitute for archiving its active children.

```sh
python3 /opt/projects/workstation/scripts/archive_directory.py archive \
  /opt/projects/.archive/PROJECT \
  --remove-local
```

Replace `PROJECT` with the selected directory. Omit `--remove-local` to upload
and verify while retaining all local contents. The default bucket is the Walle
bucket. An explicit `--snapshot YYYYMMDDTHHMMSSZ` can group several projects.

The tool inventories and hashes the source, creates a compressed archive,
uploads it, downloads the exact S3 version, checks the full archive checksum,
and checks every archived file against the original inventory. It checks for
source changes before removal. Only then can it remove payload files. Ordinary
directories remain in place; symlinks are archived and removed with the payload.

The manifest status must be `archived` after successful local removal. A status
of `verified_remote` means contents still remain locally. A status of
`removing_local_contents` means removal was interrupted. Inspect the directory
before resuming with:

```sh
python3 /opt/projects/workstation/scripts/archive_directory.py evict \
  /opt/projects/.archive/PROJECT
```

This resume command requires a verified manifest and refuses changed or new
source files. It does not upload newly created work. Keep records unchanged.

## Restore a directory

Read the project's `ARCHIVE.md`. Restore into a new path:

```sh
python3 /opt/projects/workstation/scripts/archive_directory.py restore \
  /opt/projects/.archive/PROJECT \
  --destination /opt/projects/PROJECT-restored
```

The destination must not exist. Restoration downloads the recorded S3 version,
checks its checksum and members, extracts it with bsdtar, and verifies the
restored files, permissions, and links. It does not merge with local files or
automatically remove the archive records. Use the restored path for active work.

## Failure recovery

Runtime inventories, receipts, and temporary archives live outside Git under
`~/.local/state/walle-archives/`. Credentials remain managed by the AWS CLI.
An interrupted upload or verification does not authorize local removal. Inspect
the saved manifest and source before retrying. Do not remove a staged archive
until the original source or a verified remote copy is known to exist.

The script refuses to reuse an existing staged archive or overwrite existing
local archive records. These checks prevent accidental replacement of an
unfinished operation. For a new attempt with intact local contents and no local
archive records, use a new snapshot identifier.

An interrupted restoration can leave a partial destination. Preserve it for
inspection, or remove that specific partial directory before retrying. Never
retry restoration into a directory that contains new work.

## Validation

```sh
cd /opt/projects/workstation
python3 -m unittest discover -s tests -p test_archive_directory.py -v
```

The tests exercise byte verification, missing entries, symlinks, hard links,
empty directories, macOS extended attributes, and refusal to remove changed or
unverified source contents. Real archival verifies every uploaded payload by
downloading it again. Keep the local records and the remote records together
when transferring archive ownership to a new machine.
