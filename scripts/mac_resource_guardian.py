#!/usr/bin/env python3
"""Watch free disk, swap and memory on this Mac and reclaim space safely.

Runs every five minutes from launchd. Each run measures free disk, swap,
memory pressure, the largest watched paths and the top memory processes,
and appends one JSON line to ~/.local/state/mac-resource-guardian/samples.jsonl
(rotated at 5 MiB).

While free disk is below the cleanup threshold (default 25 GiB), and only
then, it performs safe, reversible or regenerable cleanup:

- copytruncate-rotates and gzips explicitly listed logs larger than 50 MiB
  (the gzipped archive keeps the content; the active log is truncated in
  place so the writing process never loses its handle);
- deletes files older than a stated age from explicitly listed regenerable
  caches and aged top-level entries from /tmp.

It never touches source trees, git repositories or worktrees, databases,
Stoic, Ribbon Field or agent state, or anything under /opt/projects; those
are guarded explicitly and the allowlist above never names them.

Everything else (idle Colima VM disks, inactive git worktrees, runaway
processes, unlinked open files over 1 GiB) is only reported as a
recommendation with an exact command. This version never kills a process
and never deletes outside the allowlist.

Alerts go to a local macOS notification (osascript), not Ribbon Field:
during a disk or swap crisis the agent substrate may itself be crashing,
while osascript needs nothing but the local system. At most one alert per
condition per hour.

--dry-run prints what it would do and changes nothing.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

GIB = 1024 ** 3
MIB = 1024 ** 2

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "mac-resource-guardian"
SAMPLES_NAME = "samples.jsonl"
SAMPLES_MAX_BYTES = 5 * MIB
ALERTS_NAME = "alerts.json"
LOCK_NAME = "heavy-job.lock"
DEFAULT_LOCK_FILE = DEFAULT_STATE_DIR / LOCK_NAME

LOG_SIZE_LIMIT_BYTES = 50 * MIB
LOG_KEEP_ARCHIVES = 3
LOG_GLOBS = (
    "/opt/homebrew/var/log/syncthing.log",
    str(Path.home() / ".ramble" / "logs" / "*.log"),
    str(Path.home() / "Library" / "Logs" / "*.log"),
)


@dataclass(frozen=True)
class CacheClass:
    """An explicitly listed regenerable path class cleaned by age.

    mode "files" deletes files older than max_age anywhere under path and
    prunes empty directories; mode "entries" deletes whole top-level
    entries of path older than max_age.
    """

    label: str
    path: Path
    max_age: dt.timedelta
    mode: str = "files"


DEFAULT_CACHE_CLASSES = (
    CacheClass("tmp-entries", Path("/tmp"), dt.timedelta(days=2), mode="entries"),
    CacheClass("npm-cache", Path.home() / ".npm" / "_cacache", dt.timedelta(days=30)),
    CacheClass("pip-cache", Path.home() / "Library" / "Caches" / "pip", dt.timedelta(days=30)),
    CacheClass("uv-cache", Path.home() / ".cache" / "uv", dt.timedelta(days=30)),
    CacheClass("playwright-browsers", Path.home() / "Library" / "Caches" / "ms-playwright", dt.timedelta(days=60)),
    CacheClass("huggingface-hub", Path.home() / ".cache" / "huggingface", dt.timedelta(days=60)),
)

WATCHED_PATHS = (
    Path("/opt/homebrew/var/log/syncthing.log"),
    Path.home() / ".ramble" / "logs",
    Path.home() / "Library" / "Logs",
    Path.home() / "Library" / "Caches",
    Path.home() / ".cache",
    Path.home() / ".npm",
    Path.home() / ".colima",
    Path("/tmp"),
)

FORBIDDEN_ROOTS = (
    Path("/opt/projects"),
    Path.home() / ".config" / "stoic",
    Path.home() / ".local" / "state" / "agent-coord",
    Path.home() / ".colima",
    Path.home() / "Library" / "Application Support",
)
FORBIDDEN_NAMES = frozenset({".git", ".svn", ".hg"})
FORBIDDEN_SUFFIXES = frozenset({".sqlite", ".sqlite3", ".db"})

UNLINKED_OPEN_MIN_BYTES = 1 * GIB
RUNAWAY_RSS_BYTES = 3 * GIB
RUNAWAY_CPU_PCT = 150.0
WORKTREE_ROOT = Path("/opt/projects")
WORKTREE_MAX_SCAN = 60
WORKTREE_SCAN_BUDGET_SECONDS = 25
WORKTREE_IDLE_DAYS = 14


def is_forbidden(path: Path, roots=FORBIDDEN_ROOTS) -> bool:
    """True when path must never be deleted or rotated by the guardian."""
    if path.name in FORBIDDEN_NAMES:
        return True
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return True
    try:
        resolved = path.resolve()
    except OSError:
        return True
    for root in roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        if resolved == root_resolved or root_resolved in resolved.parents:
            return True
    try:
        if path.is_dir() and (path / ".git").exists():
            return True
    except OSError:
        return True
    return False


def run_command(argv, timeout=15):
    """Return stdout text of a command, or None on any failure."""
    try:
        result = subprocess.run(
            argv, check=False, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def disk_free_bytes(path="/"):
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None, None
    return usage.total, usage.free


_SWAP_FIELD = re.compile(r"(\w+)\s*=\s*([0-9.]+)\s*([KMGT])")
_SWAP_UNIT = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def parse_swap_usage(text):
    """Parse `sysctl -n vm.swapusage` output into (total_bytes, used_bytes)."""
    fields = {}
    for name, value, unit in _SWAP_FIELD.findall(text):
        fields[name] = int(float(value) * _SWAP_UNIT[unit])
    if "total" not in fields or "used" not in fields:
        return None
    return fields["total"], fields["used"]


def swap_usage():
    output = run_command(["sysctl", "-n", "vm.swapusage"])
    if output is None:
        return None
    return parse_swap_usage(output)


def memory_free_pct():
    output = run_command(["memory_pressure"])
    if output:
        match = re.search(r"free percentage:\s*([0-9]+)%", output)
        if match:
            return float(match.group(1))
    vm_stat = run_command(["vm_stat"])
    memsize = run_command(["sysctl", "-n", "hw.memsize"])
    pagesize = run_command(["sysctl", "-n", "hw.pagesize"])
    if not (vm_stat and memsize and pagesize):
        return None
    try:
        pages = {}
        for line in vm_stat.splitlines():
            match = re.match(r"Pages (\w+):\s*([0-9]+)", line)
            if match:
                pages[match.group(1)] = int(match.group(2))
        free_pages = pages.get("free", 0) + pages.get("speculative", 0)
        return round(100.0 * free_pages * int(pagesize.strip()) / int(memsize.strip()), 1)
    except (ValueError, ZeroDivisionError):
        return None


def top_memory_processes(limit=5):
    output = run_command(["ps", "-Ao", "pid=,pcpu=,rss=,comm="])
    if output is None:
        return []
    processes = []
    for line in output.splitlines():
        parts = line.split(None, 3)
        if len(parts) != 4:
            continue
        try:
            pid, pcpu, rss_kb = int(parts[0]), float(parts[1]), int(parts[2])
        except ValueError:
            continue
        processes.append(
            {"pid": pid, "cpu_pct": pcpu, "rss_bytes": rss_kb * 1024, "command": parts[3]}
        )
    processes.sort(key=lambda item: item["rss_bytes"], reverse=True)
    return processes[:limit]


def path_size_bytes(path: Path):
    """Size of a file by stat or a directory by `du -sk`; None on failure."""
    try:
        if path.is_file() or path.is_symlink():
            return path.lstat().st_size
    except OSError:
        return None
    output = run_command(["du", "-sk", str(path)], timeout=30)
    if output is None:
        return None
    try:
        return int(output.split()[0]) * 1024
    except (ValueError, IndexError):
        return None


def watched_path_sizes(paths=WATCHED_PATHS):
    sizes = []
    for path in paths:
        sizes.append({"path": str(path), "bytes": path_size_bytes(path)})
    return sizes


@dataclass
class Metrics:
    sampled_at: str
    disk_total_bytes: int | None
    disk_free_bytes: int | None
    swap_total_bytes: int | None
    swap_used_bytes: int | None
    memory_free_pct: float | None
    top_memory_processes: list
    watched_paths: list


def measure(now: dt.datetime) -> Metrics:
    total, free = disk_free_bytes()
    swap = swap_usage()
    return Metrics(
        sampled_at=now.isoformat(timespec="seconds"),
        disk_total_bytes=total,
        disk_free_bytes=free,
        swap_total_bytes=swap[0] if swap else None,
        swap_used_bytes=swap[1] if swap else None,
        memory_free_pct=memory_free_pct(),
        top_memory_processes=top_memory_processes(),
        watched_paths=watched_path_sizes(),
    )


@dataclass
class Action:
    kind: str
    path: str
    bytes: int
    detail: str
    executed: bool = False
    skipped: str | None = None
    targets: list = field(default_factory=list)


@dataclass
class Recommendation:
    subject: str
    detail: str
    command: str


def plan_log_rotation(patterns, size_limit: int) -> list:
    actions = []
    for pattern in patterns:
        for name in sorted(glob.glob(pattern)):
            path = Path(name)
            try:
                if not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError:
                continue
            if size <= size_limit:
                continue
            action = Action(
                kind="rotate-log",
                path=str(path),
                bytes=size,
                detail="{:.0f} MiB exceeds {:.0f} MiB limit".format(
                    size / MIB, size_limit / MIB
                ),
                targets=[path],
            )
            if is_forbidden(path):
                action.skipped = "forbidden path"
            actions.append(action)
    return actions


def execute_log_rotation(action: Action, now: dt.datetime, keep: int) -> None:
    path = Path(action.path)
    if is_forbidden(path):
        action.skipped = "forbidden path"
        return
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    archive = path.with_name("{}.{}.gz".format(path.name, stamp))
    try:
        with path.open("rb") as source, gzip.open(archive, "wb") as out:
            shutil.copyfileobj(source, out)
        with path.open("wb"):
            pass
    except OSError as error:
        action.skipped = "rotation failed: {}".format(error)
        archive.unlink(missing_ok=True)
        return
    archives = sorted(path.parent.glob("{}.*.gz".format(path.name)))
    for old in archives[:-keep] if keep else archives:
        try:
            old.unlink()
        except OSError:
            pass
    action.executed = True
    action.detail += "; archived to {} and truncated in place".format(archive.name)


def _aged_files(root: Path, cutoff: float):
    targets = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if not is_forbidden(Path(dirpath) / name)
        ]
        for name in filenames:
            candidate = Path(dirpath) / name
            try:
                stat = candidate.lstat()
            except OSError:
                continue
            if stat.st_mtime >= cutoff:
                continue
            if is_forbidden(candidate):
                continue
            targets.append((candidate, stat.st_size))
    return targets


def _aged_entries(root: Path, cutoff: float):
    targets = []
    try:
        children = list(root.iterdir())
    except OSError:
        return targets
    for child in children:
        try:
            stat = child.lstat()
        except OSError:
            continue
        if stat.st_mtime >= cutoff:
            continue
        if is_forbidden(child):
            continue
        targets.append((child, _entry_size(child)))
    return targets


def _entry_size(path: Path) -> int:
    try:
        if path.is_symlink() or path.is_file():
            return path.lstat().st_size
    except OSError:
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [
            name for name in dirnames if not is_forbidden(Path(dirpath) / name)
        ]
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_size
            except OSError:
                continue
    return total


def plan_cache_cleaning(classes, now: dt.datetime) -> list:
    actions = []
    for entry in classes:
        path = entry.path
        if not path.exists():
            continue
        if is_forbidden(path):
            actions.append(
                Action(
                    kind="delete-cache:" + entry.label,
                    path=str(path),
                    bytes=0,
                    detail="listed path is forbidden",
                    skipped="forbidden path",
                )
            )
            continue
        cutoff = (now - entry.max_age).timestamp()
        if entry.mode == "entries":
            targets = _aged_entries(path, cutoff)
        else:
            targets = _aged_files(path, cutoff)
        if not targets:
            continue
        actions.append(
            Action(
                kind="delete-cache:" + entry.label,
                path=str(path),
                bytes=sum(size for _, size in targets),
                detail="{} items not modified in {}+ days".format(
                    len(targets), entry.max_age.days
                ),
                targets=[target for target, _ in targets],
            )
        )
    return actions


def execute_cache_cleaning(action: Action, root: Path, prune_empty: bool) -> None:
    if is_forbidden(root):
        action.skipped = "forbidden path"
        return
    freed = 0
    for target in action.targets:
        if is_forbidden(target):
            continue
        try:
            if target.is_symlink() or target.is_file():
                freed += target.lstat().st_size
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
        except OSError:
            continue
    if prune_empty:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            current = Path(dirpath)
            if current == root:
                continue
            try:
                current.rmdir()
            except OSError:
                continue
    action.bytes = freed or action.bytes
    action.executed = True


def recommend_unlinked_open_files(min_bytes=UNLINKED_OPEN_MIN_BYTES) -> list:
    output = run_command(["lsof", "-nP", "+L1"], timeout=30)
    if output is None:
        return []
    recommendations = []
    for line in output.splitlines():
        if line.startswith("COMMAND"):
            continue
        parts = line.split(None, 9)
        if len(parts) < 10:
            continue
        try:
            size = int(parts[6])
            pid = int(parts[1])
        except ValueError:
            continue
        if size < min_bytes:
            continue
        recommendations.append(
            Recommendation(
                subject="unlinked open file held by {} (pid {})".format(parts[0], pid),
                detail="{:.1f} GiB deleted but still held open: {}".format(
                    size / GIB, parts[9]
                ),
                command="kill -TERM {}".format(pid),
            )
        )
    return recommendations


def recommend_runaway_processes() -> list:
    recommendations = []
    for process in top_memory_processes(limit=25):
        if process["pid"] in (0, 1, os.getpid()):
            continue
        if process["rss_bytes"] >= RUNAWAY_RSS_BYTES:
            recommendations.append(
                Recommendation(
                    subject="large process {} (pid {})".format(
                        process["command"], process["pid"]
                    ),
                    detail="resident memory {:.1f} GiB".format(
                        process["rss_bytes"] / GIB
                    ),
                    command="kill -TERM {}".format(process["pid"]),
                )
            )
        elif process["cpu_pct"] >= RUNAWAY_CPU_PCT:
            recommendations.append(
                Recommendation(
                    subject="runaway process {} (pid {})".format(
                        process["command"], process["pid"]
                    ),
                    detail="cpu {:.0f}%".format(process["cpu_pct"]),
                    command="kill -TERM {}".format(process["pid"]),
                )
            )
    return recommendations[:10]


def recommend_colima() -> list:
    colima_dir = Path.home() / ".colima"
    if not colima_dir.exists():
        return []
    size = path_size_bytes(colima_dir)
    if size is None or size < 1 * GIB:
        return []
    if shutil.which("colima") is None:
        return [
            Recommendation(
                subject="Colima VM disks",
                detail="{:.1f} GiB under ~/.colima and the colima CLI is missing".format(
                    size / GIB
                ),
                command="du -sh ~/.colima/_lima && ls ~/.colima/_lima",
            )
        ]
    status = run_command(["colima", "status"], timeout=10)
    if status is None:
        return [
            Recommendation(
                subject="idle Colima VM disks",
                detail="{:.1f} GiB under ~/.colima and no VM is running".format(size / GIB),
                command="colima list  # then: colima delete <profile>",
            )
        ]
    containers = run_command(["docker", "ps", "-q"], timeout=10)
    if containers is not None and not containers.strip():
        return [
            Recommendation(
                subject="Colima VM running with no containers",
                detail="{:.1f} GiB under ~/.colima; docker ps is empty".format(size / GIB),
                command="colima stop",
            )
        ]
    return []


def _worktree_last_commit(worktree: Path):
    output = run_command(
        ["git", "-C", str(worktree), "log", "-1", "--format=%ct"], timeout=5
    )
    if output is None:
        return None
    try:
        return int(output.strip())
    except ValueError:
        return None


def _worktree_dirty(worktree: Path):
    output = run_command(
        ["git", "-C", str(worktree), "status", "--porcelain"], timeout=10
    )
    if output is None:
        return None
    return bool(output.strip())


def _worktree_main_repo(worktree: Path):
    git_file = worktree / ".git"
    try:
        content = git_file.read_text()
    except OSError:
        return None
    match = re.match(r"gitdir:\s*(\S+)", content)
    if not match:
        return None
    gitdir = Path(match.group(1))
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return None


def recommend_worktrees(root=WORKTREE_ROOT, now=None, idle_days=WORKTREE_IDLE_DAYS) -> list:
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=idle_days)).timestamp()
    recommendations = []
    scanned = 0
    started = now.timestamp()
    try:
        candidates = sorted(root.iterdir())
    except OSError:
        return []
    for entry in candidates:
        if scanned >= WORKTREE_MAX_SCAN:
            break
        if dt.datetime.now(dt.timezone.utc).timestamp() - started > WORKTREE_SCAN_BUDGET_SECONDS:
            break
        git_marker = entry / ".git"
        if not entry.is_dir() or not git_marker.is_file():
            continue
        scanned += 1
        last_commit = _worktree_last_commit(entry)
        if last_commit is None or last_commit >= cutoff:
            continue
        dirty = _worktree_dirty(entry)
        main_repo = _worktree_main_repo(entry)
        age_days = int((now.timestamp() - last_commit) / 86400)
        if main_repo is None:
            command = "cat {}/.git  # locate main repo, then: git worktree remove {}".format(
                entry, entry
            )
        elif dirty:
            command = "git -C {} status  # has uncommitted changes; then: git -C {} worktree remove {}".format(
                entry, main_repo, entry
            )
        else:
            command = "git -C {} worktree remove {}".format(main_repo, entry)
        note = "idle {} days, {}".format(
            age_days, "uncommitted changes" if dirty else "clean"
        )
        if dirty is None:
            note = "idle {} days, status unknown".format(age_days)
        recommendations.append(
            Recommendation(
                subject="inactive worktree {}".format(entry),
                detail=note,
                command=command,
            )
        )
    return recommendations


def load_alert_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def alert_due(state: dict, condition: str, now: dt.datetime, interval: dt.timedelta) -> bool:
    stamp = state.get(condition)
    if not isinstance(stamp, str):
        return True
    try:
        last = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return True
    return now - dt.datetime.fromtimestamp(last.timestamp(), tz=dt.timezone.utc) >= interval


def record_alert(state: dict, condition: str, now: dt.datetime) -> None:
    state[condition] = now.strftime("%Y-%m-%dT%H:%M:%S%z")


def notify(message: str, title="Mac resource guardian") -> None:
    """Post a macOS notification; failures are ignored."""

    def escape(text):
        return text.replace("\\", "\\\\").replace('"', '\\"')

    script = 'display notification "{}" with title "{}"'.format(
        escape(message), escape(title)
    )
    try:
        subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def evaluate_alert_conditions(
    free_after_bytes, swap_used_bytes, swap_total_bytes, config
) -> list:
    conditions = []
    if free_after_bytes is not None and free_after_bytes < config.alert_free_bytes:
        conditions.append(
            (
                "disk",
                "disk low after cleanup: {:.1f} GiB free (< {:.0f} GiB)".format(
                    free_after_bytes / GIB, config.alert_free_bytes / GIB
                ),
            )
        )
    if swap_used_bytes is not None and swap_total_bytes:
        pct = 100.0 * swap_used_bytes / swap_total_bytes
        if pct > config.swap_alert_pct:
            conditions.append(
                (
                    "swap",
                    "swap at {:.0f}% of {:.1f} GiB".format(pct, swap_total_bytes / GIB),
                )
            )
    return conditions


def append_sample(state_dir: Path, sample: dict, max_bytes=SAMPLES_MAX_BYTES) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    samples = state_dir / SAMPLES_NAME
    try:
        if samples.exists() and samples.stat().st_size > max_bytes:
            os.replace(samples, state_dir / (SAMPLES_NAME + ".1"))
    except OSError:
        pass
    with samples.open("a") as handle:
        handle.write(json.dumps(sample, sort_keys=True) + "\n")


@dataclass
class Config:
    state_dir: Path = DEFAULT_STATE_DIR
    cleanup_free_bytes: int = 25 * GIB
    alert_free_bytes: int = 15 * GIB
    swap_alert_pct: float = 90.0
    alert_interval: dt.timedelta = dt.timedelta(hours=1)
    log_patterns: tuple = LOG_GLOBS
    log_size_limit: int = LOG_SIZE_LIMIT_BYTES
    log_keep: int = LOG_KEEP_ARCHIVES
    cache_classes: tuple = DEFAULT_CACHE_CLASSES
    dry_run: bool = False


@dataclass
class Report:
    metrics: Metrics
    cleanup_gate_open: bool
    actions: list
    recommendations: list
    alerts: list
    free_after_bytes: int | None
    dry_run: bool


def run(config: Config, now=None) -> Report:
    now = now or dt.datetime.now(dt.timezone.utc)
    metrics = measure(now)
    free = metrics.disk_free_bytes
    gate_open = free is not None and free < config.cleanup_free_bytes

    log_actions = []
    cache_actions = []
    if gate_open or config.dry_run:
        log_actions = plan_log_rotation(config.log_patterns, config.log_size_limit)
        cache_actions = plan_cache_cleaning(config.cache_classes, now)
    if gate_open and not config.dry_run:
        for action in log_actions:
            if not action.skipped:
                execute_log_rotation(action, now, config.log_keep)
        for action in cache_actions:
            if not action.skipped:
                execute_cache_cleaning(
                    action,
                    Path(action.path),
                    prune_empty=not action.kind.endswith(":tmp-entries"),
                )
    actions = log_actions + cache_actions

    executed = [a for a in actions if a.executed]
    if executed:
        _, free_after = disk_free_bytes()
    elif config.dry_run and gate_open:
        free_after = free + sum(a.bytes for a in actions if not a.skipped)
    else:
        free_after = free

    swap_pct = None
    if metrics.swap_used_bytes is not None and metrics.swap_total_bytes:
        swap_pct = 100.0 * metrics.swap_used_bytes / metrics.swap_total_bytes

    recommendations = []
    if config.dry_run or gate_open or (swap_pct is not None and swap_pct > config.swap_alert_pct):
        recommendations.extend(recommend_runaway_processes())
        recommendations.extend(recommend_unlinked_open_files())
        recommendations.extend(recommend_colima())
        recommendations.extend(recommend_worktrees(now=now))

    conditions = evaluate_alert_conditions(
        free_after, metrics.swap_used_bytes, metrics.swap_total_bytes, config
    )
    alert_path = config.state_dir / ALERTS_NAME
    state = load_alert_state(alert_path)
    alerts = []
    state_changed = False
    for condition, message in conditions:
        due = alert_due(state, condition, now, config.alert_interval)
        if due and not config.dry_run:
            notify(message)
            record_alert(state, condition, now)
            state_changed = True
        alerts.append(
            {
                "condition": condition,
                "message": message,
                "due": due,
                "sent": due and not config.dry_run,
            }
        )
    if state_changed:
        config.state_dir.mkdir(parents=True, exist_ok=True)
        alert_path.write_text(json.dumps(state, sort_keys=True))

    if not config.dry_run:
        sample = dataclasses.asdict(metrics)
        sample["cleanup"] = {
            "gate_open": gate_open,
            "actions": [
                {
                    "kind": a.kind,
                    "path": a.path,
                    "bytes": a.bytes,
                    "executed": a.executed,
                    "skipped": a.skipped,
                }
                for a in actions
            ],
        }
        sample["alerts"] = [a["condition"] for a in alerts if a["sent"]]
        append_sample(config.state_dir, sample)

    return Report(
        metrics=metrics,
        cleanup_gate_open=gate_open,
        actions=actions,
        recommendations=recommendations,
        alerts=alerts,
        free_after_bytes=free_after,
        dry_run=config.dry_run,
    )


def _fmt_gib(value):
    if value is None:
        return "unknown"
    return "{:.1f} GiB".format(value / GIB)


def render(report: Report) -> str:
    metrics = report.metrics
    lines = []
    mode = "DRY RUN (nothing changed)" if report.dry_run else "run"
    lines.append("mac-resource-guardian {} — {}".format(mode, metrics.sampled_at))
    swap_pct = None
    if metrics.swap_used_bytes is not None and metrics.swap_total_bytes:
        swap_pct = 100.0 * metrics.swap_used_bytes / metrics.swap_total_bytes
    lines.append(
        "disk: {} free of {}; swap: {} of {}{}; memory free: {}".format(
            _fmt_gib(metrics.disk_free_bytes),
            _fmt_gib(metrics.disk_total_bytes),
            _fmt_gib(metrics.swap_used_bytes),
            _fmt_gib(metrics.swap_total_bytes),
            " ({:.0f}%)".format(swap_pct) if swap_pct is not None else "",
            "{}%".format(metrics.memory_free_pct)
            if metrics.memory_free_pct is not None
            else "unknown",
        )
    )
    if report.cleanup_gate_open:
        gate = "OPEN ({:.1f} GiB free < threshold)".format(
            (metrics.disk_free_bytes or 0) / GIB
        )
    else:
        gate = "closed ({:.1f} GiB free >= threshold; cleanup would not run now)".format(
            (metrics.disk_free_bytes or 0) / GIB
        )
    if report.dry_run and not report.cleanup_gate_open:
        gate += " — plan below shown for inspection"
    lines.append("cleanup gate: " + gate)

    reclaimable = sum(a.bytes for a in report.actions if not a.skipped)
    if report.actions:
        lines.append("cleanup plan, {} reclaimable:".format(_fmt_gib(reclaimable)))
        for action in report.actions:
            verb = "would " if report.dry_run else ""
            if action.skipped:
                lines.append(
                    "  SKIP {} {} ({})".format(action.kind, action.path, action.skipped)
                )
            else:
                lines.append(
                    "  {}{} {} — {} ({})".format(
                        verb, action.kind, action.path, _fmt_gib(action.bytes), action.detail
                    )
                )
    else:
        lines.append("cleanup plan: nothing to reclaim")
    lines.append("free after cleanup: {}".format(_fmt_gib(report.free_after_bytes)))

    if report.alerts:
        for alert in report.alerts:
            if report.dry_run:
                state = "would notify" if alert["due"] else "rate-limited, would not notify"
            else:
                state = "notified" if alert["sent"] else "rate-limited"
            lines.append("alert[{}]: {} ({})".format(alert["condition"], alert["message"], state))
    else:
        lines.append("alerts: none")

    if report.recommendations:
        lines.append("recommendations (no automatic action):")
        for item in report.recommendations:
            lines.append("  {}: {}".format(item.subject, item.detail))
            lines.append("    $ {}".format(item.command))
    else:
        lines.append("recommendations: none")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would happen and change nothing",
    )
    parser.add_argument(
        "--cleanup-gb",
        type=float,
        default=25.0,
        help="run cleanup only below this much free disk (default 25)",
    )
    parser.add_argument(
        "--alert-gb",
        type=float,
        default=15.0,
        help="alert when free disk stays below this after cleanup (default 15)",
    )
    parser.add_argument(
        "--swap-alert-pct",
        type=float,
        default=90.0,
        help="alert above this swap usage percentage (default 90)",
    )
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    args = parser.parse_args(argv)

    config = Config(
        state_dir=args.state_dir,
        cleanup_free_bytes=int(args.cleanup_gb * GIB),
        alert_free_bytes=int(args.alert_gb * GIB),
        swap_alert_pct=args.swap_alert_pct,
        dry_run=args.dry_run,
    )
    report = run(config)
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
