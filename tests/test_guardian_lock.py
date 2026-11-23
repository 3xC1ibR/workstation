import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
guardian_spec = importlib.util.spec_from_file_location(
    "mac_resource_guardian", SCRIPTS / "mac_resource_guardian.py"
)
guardian = importlib.util.module_from_spec(guardian_spec)
sys.modules["mac_resource_guardian"] = guardian
guardian_spec.loader.exec_module(guardian)

lock_spec = importlib.util.spec_from_file_location(
    "guardian_lock", SCRIPTS / "guardian_lock.py"
)
lock = importlib.util.module_from_spec(lock_spec)
sys.modules["guardian_lock"] = lock
lock_spec.loader.exec_module(lock)

GIB = 1024 ** 3


def dead_pid():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def healthy_resources(monkeypatch):
    monkeypatch.setattr(guardian, "disk_free_bytes", lambda path="/": (460 * GIB, 100 * GIB))
    monkeypatch.setattr(guardian, "swap_usage", lambda: (10 * GIB, 1 * GIB))
    monkeypatch.setattr(guardian, "memory_free_pct", lambda: 50.0)


def acquire(lock_path, kind="build", holder="test-agent"):
    return lock.acquire(lock_path, kind, holder, 15 * GIB, 85.0, 8.0)


def test_acquire_creates_lock(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    code, message = acquire(lock_path)
    assert code == lock.EXIT_ACQUIRED
    assert "acquired" in message
    record = json.loads(lock_path.read_text())
    assert record["pid"] == os.getpid()
    assert record["kind"] == "build"
    assert record["token"]


def test_acquire_refused_while_live_holder(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    lock_path.write_text(json.dumps(
        {"pid": 1, "kind": "build", "holder": "launchd", "acquired_at": "2026-11-23T00:00:00+00:00", "token": "abc"}
    ))
    code, message = acquire(lock_path)
    assert code == lock.EXIT_HELD
    assert "pid 1" in message
    assert json.loads(lock_path.read_text())["token"] == "abc"


def test_acquire_takes_over_stale_lock(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    gone = dead_pid()
    lock_path.write_text(json.dumps(
        {"pid": gone, "kind": "whisper", "holder": "old-agent", "acquired_at": "2026-11-22T00:00:00+00:00", "token": "old"}
    ))
    code, message = acquire(lock_path)
    assert code == lock.EXIT_ACQUIRED
    assert "stale" in message
    assert json.loads(lock_path.read_text())["pid"] == os.getpid()


def test_acquire_refused_on_low_disk(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    monkeypatch.setattr(guardian, "disk_free_bytes", lambda path="/": (460 * GIB, 10 * GIB))
    code, message = acquire(tmp_path / "heavy-job.lock")
    assert code == lock.EXIT_RESOURCES
    assert "10.0 GiB" in message
    assert not (tmp_path / "heavy-job.lock").exists()


def test_acquire_refused_on_high_swap(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    monkeypatch.setattr(guardian, "swap_usage", lambda: (10 * GIB, 9 * GIB))
    code, message = acquire(tmp_path / "heavy-job.lock")
    assert code == lock.EXIT_RESOURCES
    assert "swap" in message


def test_acquire_refused_on_low_memory(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    monkeypatch.setattr(guardian, "memory_free_pct", lambda: 3.0)
    code, message = acquire(tmp_path / "heavy-job.lock")
    assert code == lock.EXIT_RESOURCES
    assert "memory" in message


def test_acquire_tolerates_failed_measurement(tmp_path, monkeypatch):
    monkeypatch.setattr(guardian, "disk_free_bytes", lambda path="/": (None, None))
    monkeypatch.setattr(guardian, "swap_usage", lambda: None)
    monkeypatch.setattr(guardian, "memory_free_pct", lambda: None)
    code, _ = acquire(tmp_path / "heavy-job.lock")
    assert code == lock.EXIT_ACQUIRED


def test_release_requires_matching_token(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    acquire(lock_path)
    token = json.loads(lock_path.read_text())["token"]

    code, message = lock.release(lock_path, token="wrong")
    assert code == lock.EXIT_CONFLICT
    assert lock_path.exists()

    code, message = lock.release(lock_path, token=token)
    assert code == lock.EXIT_ACQUIRED
    assert not lock_path.exists()


def test_release_own_pid_and_free_lock(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    acquire(lock_path)
    code, _ = lock.release(lock_path)
    assert code == lock.EXIT_ACQUIRED
    code, message = lock.release(lock_path)
    assert code == lock.EXIT_ACQUIRED
    assert "not held" in message


def test_release_other_holder_requires_credential(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    gone = dead_pid()
    lock_path.write_text(json.dumps(
        {"pid": gone, "kind": "build", "holder": "other", "acquired_at": "2026-11-23T00:00:00+00:00", "token": "xyz"}
    ))
    code, _ = lock.release(lock_path)
    assert code == lock.EXIT_CONFLICT
    code, _ = lock.release(lock_path, pid=gone)
    assert code == lock.EXIT_ACQUIRED


def test_status(tmp_path, monkeypatch):
    healthy_resources(monkeypatch)
    lock_path = tmp_path / "heavy-job.lock"
    assert lock.status(lock_path) == "free"
    acquire(lock_path)
    assert lock.status(lock_path).startswith("held")
