#!/usr/bin/env python3
"""Extend supported harness retention without replacing unrelated settings."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tomllib


def configure(home=None, state=None):
    home = Path(home or Path.home())
    state = Path(state or home / ".local/state/agent-data-backups")
    copies = state / "configuration-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    changed = []
    def write(path, text):
        if path.exists() and path.read_text() == text:
            return
        copies.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            destination = copies / path.relative_to(home)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".retention-pending")
        temporary.write_text(text)
        temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
        temporary.replace(path)
        changed.append(str(path))
    def edit_json(relative, edit):
        path = home / relative
        value = json.loads(path.read_text()) if path.exists() else {}
        previous = json.dumps(value, sort_keys=True)
        edit(value)
        if json.dumps(value, sort_keys=True) == previous:
            return
        write(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    edit_json(".claude/settings.json", lambda value: value.update(cleanupPeriodDays=36500))
    # Muse's documented unset value is indefinite; do not introduce an age limit.
    edit_json(".config/muse/settings.json", lambda value: value.pop("session_retention_days", None))
    def gemini(value):
        value.setdefault("general", {}).setdefault("sessionRetention", {})["enabled"] = False
    edit_json(".gemini/settings.json", gemini)
    path = home / ".codex/config.toml"
    text = path.read_text() if path.exists() else ""
    # Preserve comments and all non-history TOML verbatim.
    lines, output, section, found = text.splitlines(keepends=True), [], None, False
    for line in lines:
        match = re.match(r"^\s*\[([^\]]+)\]", line)
        if match:
            if section == "history":
                output.append('persistence = "save-all"\n')
            section = match.group(1).strip()
            found |= section == "history"
        if section == "history" and re.match(r"^\s*(persistence|max_bytes)\s*=", line):
            continue
        if section is None and re.match(r"^\s*history\.(persistence|max_bytes)\s*=", line):
            continue
        output.append(line)
    if section == "history":
        if output and not output[-1].endswith("\n"):
            output.append("\n")
        output.append('persistence = "save-all"\n')
    if not found:
        output.append('\n[history]\npersistence = "save-all"\n')
    updated = "".join(output)
    parsed = tomllib.loads(updated)
    assert parsed["history"]["persistence"] == "save-all" and "max_bytes" not in parsed["history"]
    write(path, updated)
    return changed


if __name__ == "__main__":
    os.umask(0o077)
    print(json.dumps({"changed": configure()}, indent=2))
