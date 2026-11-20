#!/usr/bin/env python3
"""Give Claude Code and Codex the same personal skills.

Codex reads ~/.agents/skills; Claude Code reads ~/.claude/skills. Personal
skills are installed in ~/.agents/skills (see ~/.claude/CLAUDE.md, "Personal
skills"); skills synchronized from claude.ai arrive only under
~/.claude/skills/synced/<account>/<name>, whose account directory can change.

This program links each skill into the directory the other client reads:

* every ~/.agents/skills/<name> into ~/.claude/skills/<name>, using the
  skill's agents/claude.md entrypoint when it provides one;
* every portable claude.ai skill into ~/.agents/skills/<name>.

It never overwrites a real file or directory, only creates links and repairs
links that it owns (those pointing into a skill source). Run it after
installing a skill; it is idempotent. Use --dry-run to preview.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

HOME = Path.home()
SHARED_DIRECTORY = HOME / ".agents" / "skills"
CLAUDE_DIRECTORY = HOME / ".claude" / "skills"
SYNCED_DIRECTORY = CLAUDE_DIRECTORY / "synced"

# claude.ai skills that depend on Claude-only tools or connectors, or that
# duplicate a skill Codex already bundles.
CLAUDE_ONLY_SKILLS = frozenset({
    "built-in-browser",
    "chrome-browser",
    "computer-use",
    "docs",
    "google-workspace",
    "import-memory",
    "morning",
    "skill-creator",
})


def synced_skills() -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not SYNCED_DIRECTORY.is_dir():
        return found
    for entry in sorted(SYNCED_DIRECTORY.glob("*/*/SKILL.md")):
        found.setdefault(entry.parent.name, entry.parent)
    return found


def shared_skills() -> dict[str, Path]:
    return {
        entry.name: entry
        for entry in sorted(SHARED_DIRECTORY.iterdir())
        if (entry / "SKILL.md").is_file()
    }


def owned_link(path: Path) -> bool:
    """A link this program may replace: a symbolic link, possibly dangling."""
    return path.is_symlink()


def place_link(link: Path, target: Path, dry_run: bool, actions: list[str]) -> None:
    if link.is_symlink() and link.exists() and link.resolve() == target.resolve():
        return
    if link.exists() and not owned_link(link):
        actions.append(f"kept existing {link}")
        return
    actions.append(f"link {link} -> {target}")
    if dry_run:
        return
    if link.is_symlink():
        link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)


def link_for_claude(name: str, source: Path, dry_run: bool, actions: list[str]) -> None:
    destination = CLAUDE_DIRECTORY / name
    resolved = source.resolve()
    claude_entrypoint = resolved / "agents" / "claude.md"
    if not claude_entrypoint.is_file():
        place_link(destination, source, dry_run, actions)
        return
    # Claude-specific entrypoint: a directory holding SKILL.md -> agents/claude.md.
    if destination.exists() and not destination.is_dir():
        actions.append(f"kept existing {destination}")
        return
    if destination.is_symlink():
        actions.append(f"kept existing {destination}")
        return
    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)
    place_link(destination / "SKILL.md", claude_entrypoint, dry_run, actions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    actions: list[str] = []

    for name, source in synced_skills().items():
        if name in CLAUDE_ONLY_SKILLS:
            continue
        destination = SHARED_DIRECTORY / name
        if destination.exists() and not destination.is_symlink():
            continue
        if destination.is_symlink() and not str(os.readlink(destination)).startswith(str(SYNCED_DIRECTORY)):
            continue
        place_link(destination, source, arguments.dry_run, actions)

    synced_names = set(synced_skills())
    for name, source in shared_skills().items():
        if source.is_symlink() and str(os.readlink(source)).startswith(str(SYNCED_DIRECTORY)):
            continue  # already visible to Claude through synced/
        if name in synced_names:
            continue
        link_for_claude(name, source, arguments.dry_run, actions)

    for line in actions:
        print(line)
    print(f"{len(actions)} change(s){' planned' if arguments.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
