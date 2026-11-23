#!/usr/bin/env python3
"""Advisory heavy-job lock for memory- and disk-hungry work on this Mac.

Agents run `guardian_lock.py acquire --kind build` before Docker/Colima
builds, Whisper batches or full browser test suites so that only one heavy
job runs at a time and never into an already-exhausted machine. Acquire
refuses, saying why, when another live holder holds the lock or when free
disk, swap headroom or free memory are below the floors. A holder whose
process has died leaves a stale lock, which the next acquirer takes over.

The lock is advisory: it coordinates well-behaved callers and does not
prevent a process that skips it. Lock file:
~/.local/state/mac-resource-guardian/heavy-job.lock
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import socket
import sys
import uuid
from pathlib import Path

try:
    import mac_resource_guardian as guardian
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mac_resource_guardian as guardian

EXIT_ACQUIRED = 0
EXIT_HELD = 1
EXIT_RESOURCES = 2
EXIT_CONFLICT = 3


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock(path: Path):
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "pid" not in data:
        return None
    return data


def describe(holder: dict) -> str:
    return "pid {} kind {} acquired {} by {}".format(
        holder.get("pid"),
        holder.get("kind"),
        holder.get("acquired_at"),
        holder.get("holder"),
    )


def check_resources(min_free_bytes: int, max_swap_pct: float, min_mem_free_pct: float):
    """Return a refusal string when the machine is low, else None.

    A measurement that fails is treated as healthy: the lock is advisory
    and the guardian daemon keeps watching regardless.
    """
    total, free = guardian.disk_free_bytes()
    if free is not None and free < min_free_bytes:
        return "only {:.1f} GiB free disk (< {:.0f} GiB floor)".format(
            free / guardian.GIB, min_free_bytes / guardian.GIB
        )
    swap = guardian.swap_usage()
    if swap and swap[0]:
        pct = 100.0 * swap[1] / swap[0]
        if pct > max_swap_pct:
            return "swap at {:.0f}% (> {:.0f}% ceiling)".format(pct, max_swap_pct)
    mem_pct = guardian.memory_free_pct()
    if mem_pct is not None and mem_pct < min_mem_free_pct:
        return "only {:.0f}% memory free (< {:.0f}% floor)".format(
            mem_pct, min_mem_free_pct
        )
    return None


def acquire(path: Path, kind: str, holder: str, min_free_bytes: int,
            max_swap_pct: float, min_mem_free_pct: float, now=None):
    """Try to take the lock. Returns (exit_code, message)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    existing = read_lock(path)
    takeover = None
    if existing is not None:
        pid = existing.get("pid")
        if isinstance(pid, int) and pid != os.getpid() and pid_alive(pid):
            return EXIT_HELD, "refused: lock held by {}".format(describe(existing))
        if isinstance(pid, int) and pid != os.getpid():
            takeover = "took over stale lock from dead {}".format(describe(existing))
            try:
                path.unlink()
            except OSError:
                pass

    refusal = check_resources(min_free_bytes, max_swap_pct, min_mem_free_pct)
    if refusal:
        return EXIT_RESOURCES, "refused: " + refusal

    record = {
        "pid": os.getpid(),
        "kind": kind,
        "holder": holder,
        "acquired_at": now.isoformat(timespec="seconds"),
        "token": uuid.uuid4().hex,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        current = read_lock(path)
        if current is not None:
            return EXIT_HELD, "refused: lock held by {}".format(describe(current))
        return EXIT_CONFLICT, "refused: lock race lost; retry"
    with os.fdopen(descriptor, "w") as handle:
        handle.write(json.dumps(record, sort_keys=True))
    message = "acquired: token {} ({})".format(record["token"], describe(record))
    if takeover:
        message += "; " + takeover
    return EXIT_ACQUIRED, message


def release(path: Path, token=None, pid=None):
    """Release the lock. Returns (exit_code, message)."""
    existing = read_lock(path)
    if existing is None:
        return EXIT_ACQUIRED, "free: lock not held"
    if token is not None and token != existing.get("token"):
        return EXIT_CONFLICT, "refused: token does not match {}".format(describe(existing))
    if token is None and pid is not None and pid != existing.get("pid"):
        return EXIT_CONFLICT, "refused: pid does not match {}".format(describe(existing))
    if token is None and pid is None and existing.get("pid") != os.getpid():
        return EXIT_CONFLICT, (
            "refused: lock held by {}; pass --token or --pid to release another holder"
        ).format(describe(existing))
    try:
        path.unlink()
    except OSError as error:
        return EXIT_CONFLICT, "release failed: {}".format(error)
    return EXIT_ACQUIRED, "released: {}".format(describe(existing))


def status(path: Path):
    existing = read_lock(path)
    if existing is None:
        return "free"
    state = "held" if pid_alive(existing.get("pid", -1)) else "stale"
    return "{}: {}".format(state, json.dumps(existing, sort_keys=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lock-file", type=Path, default=guardian.DEFAULT_LOCK_FILE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire_parser = subparsers.add_parser("acquire", help="take the lock")
    acquire_parser.add_argument("--kind", required=True,
                                help="job class, for example build, whisper, browser-tests")
    acquire_parser.add_argument("--holder", default=None,
                                help="who is asking (default: user@host)")
    acquire_parser.add_argument("--min-free-gb", type=float, default=15.0,
                                help="refuse below this much free disk (default 15)")
    acquire_parser.add_argument("--max-swap-pct", type=float, default=85.0,
                                help="refuse above this swap percentage (default 85)")
    acquire_parser.add_argument("--min-mem-free-pct", type=float, default=8.0,
                                help="refuse below this free memory percentage (default 8)")

    release_parser = subparsers.add_parser("release", help="release the lock")
    release_parser.add_argument("--token", default=None)
    release_parser.add_argument("--pid", type=int, default=None)

    subparsers.add_parser("status", help="print the lock holder")

    args = parser.parse_args(argv)

    if args.command == "acquire":
        holder = args.holder or "{}@{}".format(getpass.getuser(), socket.gethostname())
        code, message = acquire(
            args.lock_file,
            args.kind,
            holder,
            int(args.min_free_gb * guardian.GIB),
            args.max_swap_pct,
            args.min_mem_free_pct,
        )
        print(message)
        return code
    if args.command == "release":
        code, message = release(args.lock_file, token=args.token, pid=args.pid)
        print(message)
        return code
    print(status(args.lock_file))
    return EXIT_ACQUIRED


if __name__ == "__main__":
    sys.exit(main())
