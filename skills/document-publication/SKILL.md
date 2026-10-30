---
name: document-publication
description: Make a selected local Markdown report readable on a phone, iPad, or other device through the existing private Tailscale research reader. Use for requests to publish a local document to the reader or return a phone-readable link; excludes public website hosting and editing document content.
---

# Document publication

Use `publish-document` to publish an explicitly selected Markdown file through the existing private reader. It renders phone-friendly HTML, registers only that file, and returns a stable HTTPS link after checking that the served page matches the rendered content. It preserves the source file and existing reader links.

```sh
publish-document /absolute/path/report.md
publish-document /absolute/path/report.md --mode live
publish-document /absolute/path/report.md --mode snapshot --json
```

New publications default to **snapshot**: later source edits do not change the published copy. Repeat the command to publish a new revision at the same URL. **Live** publications follow source changes within 30 seconds while the reader is running. Repeating a command without `--mode` retains the document's current mode. Use live mode when the user requests continuing updates; otherwise use snapshots. Publishing the named file does not authorize publishing neighboring files, linked citations, or whole folders.

Return the verified URL and say whether the publication is a snapshot or live. Tailscale must be connected on the reading device, and this Mac must stay awake and online. The reader is private to devices/users permitted by the tailnet; it does not require Ribbon Field device pairing. This workflow does not provide public or offline hosting.

For diagnosis and withdrawal:

```sh
publish-document --list --json
publish-document --check --json
publish-document --remove PUBLICATION_ID
```

`--list` regenerates pages and reports unreadable sources. `--check` additionally verifies every registered HTTPS page and exits nonzero for source or delivery failures. When a live source disappears, the last good page stays available with a stale-source notice until the source returns or publication is withdrawn. `--remove` withdraws the published page and snapshot, preserving the original file.

An unsuccessful publish can leave a registration in place, but emits no successful link. Inspect `--list`/`--check`, repair the concrete failure, and repeat the same command; do not add public exposure, alter unrelated Tailscale routes, or restart Ribbon Field agents to repair document delivery.

## Installation and maintenance

The installed skill is a symlink to `/opt/projects/workstation/skills/document-publication`. Edit and commit that source. Runtime state, snapshots, generated pages, receipts, logs, and migration backups live in `/opt/projects/out/_reader`, outside the repository. The existing launchd reader serves only generated HTML on `127.0.0.1:8767`, behind the existing `/reader` Tailscale route.

If the command is missing, use the executable at [scripts/publish_document.py](scripts/publish_document.py), or install it with:

```sh
/Users/walle/miniforge3/bin/python3 /opt/projects/workstation/skills/document-publication/scripts/install.py
```

The installer requires the existing private HTTPS Tailscale `/reader` route. It adopts the legacy report manifest as explicit file registrations, preserves old URLs, saves migration backups, installs the command/skill symlinks, and restarts only the reader once. Ordinary publications require no restarts. Do not run the installer routinely or use it to create unrelated services. Python uses the existing Miniforge environment with `markdown-it-py`; no package installation is needed on this Mac.

Validate source changes with:

```sh
/Users/walle/miniforge3/bin/python3 -W error::ResourceWarning -m unittest discover -s /opt/projects/workstation/skills/document-publication/tests -v
```
