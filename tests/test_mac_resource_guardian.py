import datetime as dt
import gzip
import importlib.util
import json
import os
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mac_resource_guardian.py"
spec = importlib.util.spec_from_file_location("mac_resource_guardian", SCRIPT)
guardian = importlib.util.module_from_spec(spec)
sys.modules["mac_resource_guardian"] = guardian
spec.loader.exec_module(guardian)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)
GIB = 1024 ** 3


def fake_metrics(free_bytes, swap_used=0, swap_total=10 * GIB, mem_pct=50.0):
    return guardian.Metrics(
        sampled_at=NOW.isoformat(timespec="seconds"),
        disk_total_bytes=460 * GIB,
        disk_free_bytes=free_bytes,
        swap_total_bytes=swap_total,
        swap_used_bytes=swap_used,
        memory_free_pct=mem_pct,
        top_memory_processes=[],
        watched_paths=[],
    )


def make_config(tmp_path, **overrides):
    values = dict(
        state_dir=tmp_path / "state",
        cleanup_free_bytes=25 * GIB,
        alert_free_bytes=15 * GIB,
        swap_alert_pct=90.0,
        log_patterns=(),
        cache_classes=(),
    )
    values.update(overrides)
    return guardian.Config(**values)


def test_parse_swap_usage():
    text = "total = 10240.00M  used = 9286.00M  free = 954.00M  (encrypted)"
    total, used = guardian.parse_swap_usage(text)
    assert total == 10 * 1024 ** 3
    assert used == 9286 * 1024 ** 2
    assert guardian.parse_swap_usage("garbage") is None


def test_cleanup_gate_respects_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(guardian, "measure", lambda now: fake_metrics(30 * GIB))
    report = guardian.run(make_config(tmp_path), now=NOW)
    assert report.cleanup_gate_open is False
    assert report.actions == []

    monkeypatch.setattr(guardian, "measure", lambda now: fake_metrics(10 * GIB))
    monkeypatch.setattr(guardian, "disk_free_bytes", lambda path="/": (460 * GIB, 10 * GIB))
    log = tmp_path / "big.log"
    log.write_bytes(b"x" * 2048)
    config = make_config(
        tmp_path, log_patterns=(str(tmp_path / "*.log"),), log_size_limit=1000
    )
    report = guardian.run(config, now=NOW)
    assert report.cleanup_gate_open is True
    assert report.actions and all(a.executed for a in report.actions)


def test_log_rotation_copytruncate_preserves_content(tmp_path):
    log = tmp_path / "syncthing.log"
    content = b"log line\n" * 5000
    log.write_bytes(content)
    actions = guardian.plan_log_rotation((str(tmp_path / "*.log"),), size_limit=1000)
    assert len(actions) == 1
    action = actions[0]
    guardian.execute_log_rotation(action, NOW, keep=3)
    assert action.executed
    assert log.read_bytes() == b""
    archives = list(tmp_path.glob("syncthing.log.*.gz"))
    assert len(archives) == 1
    with gzip.open(archives[0], "rb") as handle:
        assert handle.read() == content


def test_log_rotation_keeps_only_newest_archives(tmp_path):
    log = tmp_path / "ramble.log"
    for index in range(5):
        stamp = "202611{:02d}T000000Z".format(index + 1)
        (tmp_path / "ramble.log.{}.gz".format(stamp)).write_bytes(b"old")
    log.write_bytes(b"x" * 2048)
    (action,) = guardian.plan_log_rotation((str(log),), size_limit=1000)
    guardian.execute_log_rotation(action, NOW, keep=3)
    remaining = sorted(tmp_path.glob("ramble.log.*.gz"))
    assert len(remaining) == 3
    assert remaining[-1].name == "ramble.log.{}.gz".format(NOW.strftime("%Y%m%dT%H%M%SZ"))


def test_log_under_limit_not_planned(tmp_path):
    log = tmp_path / "small.log"
    log.write_bytes(b"tiny")
    assert guardian.plan_log_rotation((str(log),), size_limit=1000) == []


def test_cache_age_delete_files_mode(tmp_path):
    cache = tmp_path / "cache"
    old_dir = cache / "old"
    old_dir.mkdir(parents=True)
    old_file = old_dir / "stale.bin"
    old_file.write_bytes(b"old data")
    fresh_file = cache / "fresh.bin"
    fresh_file.write_bytes(b"fresh")
    old_time = (NOW - dt.timedelta(days=45)).timestamp()
    os.utime(old_file, (old_time, old_time))
    os.utime(old_dir, (old_time, old_time))

    classes = (guardian.CacheClass("test-cache", cache, dt.timedelta(days=30)),)
    actions = guardian.plan_cache_cleaning(classes, NOW)
    assert len(actions) == 1
    assert actions[0].targets == [old_file]
    guardian.execute_cache_cleaning(actions[0], cache, prune_empty=True)
    assert not old_file.exists()
    assert not old_dir.exists()
    assert fresh_file.exists()
    assert cache.exists()


def test_cache_age_delete_entries_mode(tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    old_dir = tmp / "old-build"
    old_dir.mkdir()
    (old_dir / "artifact.o").write_bytes(b"object")
    fresh_dir = tmp / "fresh-build"
    fresh_dir.mkdir()
    old_time = (NOW - dt.timedelta(days=5)).timestamp()
    for root, dirnames, filenames in os.walk(old_dir):
        os.utime(root, (old_time, old_time))
        for name in filenames:
            os.utime(Path(root) / name, (old_time, old_time))

    classes = (guardian.CacheClass("tmp-entries", tmp, dt.timedelta(days=2), mode="entries"),)
    (action,) = guardian.plan_cache_cleaning(classes, NOW)
    guardian.execute_cache_cleaning(action, tmp, prune_empty=False)
    assert not old_dir.exists()
    assert fresh_dir.exists()


def test_forbidden_paths_are_never_touched(tmp_path):
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    database = tmp_path / "records.sqlite"
    database.write_bytes(b"db")
    stale = tmp_path / "stale.bin"
    stale.write_bytes(b"x")
    old_time = (NOW - dt.timedelta(days=90)).timestamp()
    for path in (repo, database, stale):
        os.utime(path, (old_time, old_time))
    os.utime(repo / ".git", (old_time, old_time))

    assert guardian.is_forbidden(repo)
    assert guardian.is_forbidden(repo / ".git")
    assert guardian.is_forbidden(database)
    assert guardian.is_forbidden(tmp_path / "sub", roots=(tmp_path,))
    assert not guardian.is_forbidden(stale)

    classes = (guardian.CacheClass("tmp-entries", tmp_path, dt.timedelta(days=2), mode="entries"),)
    (action,) = guardian.plan_cache_cleaning(classes, NOW)
    assert action.targets == [stale]
    guardian.execute_cache_cleaning(action, tmp_path, prune_empty=False)
    assert repo.exists() and database.exists() and not stale.exists()


def test_forbidden_log_rotation_is_skipped(tmp_path):
    log = tmp_path / "x.log"
    log.write_bytes(b"x" * 2048)
    (action,) = guardian.plan_log_rotation((str(log),), size_limit=1000)
    assert action.skipped is None
    guardian.execute_log_rotation(action, NOW, keep=3)
    assert action.executed
    skipped = guardian.plan_log_rotation((str(tmp_path / "state.sqlite"),), size_limit=1)
    assert skipped == []


def test_dry_run_changes_nothing(tmp_path, monkeypatch):
    log = tmp_path / "big.log"
    original = b"x" * 4096
    log.write_bytes(original)
    monkeypatch.setattr(guardian, "measure", lambda now: fake_metrics(5 * GIB))
    config = make_config(
        tmp_path,
        log_patterns=(str(log),),
        log_size_limit=1000,
        dry_run=True,
    )
    report = guardian.run(config, now=NOW)
    assert report.cleanup_gate_open is True
    assert report.actions and not any(a.executed for a in report.actions)
    assert log.read_bytes() == original
    assert not (tmp_path / "state").exists()


def test_dry_run_estimates_free_after_cleanup(tmp_path, monkeypatch):
    log = tmp_path / "big.log"
    with log.open("wb") as handle:
        handle.truncate(2 * GIB)  # sparse: 2 GiB by stat, no real blocks
    monkeypatch.setattr(guardian, "measure", lambda now: fake_metrics(10 * GIB))
    config = make_config(
        tmp_path, log_patterns=(str(log),), log_size_limit=1000, dry_run=True
    )
    report = guardian.run(config, now=NOW)
    assert report.free_after_bytes == 12 * GIB


def test_alert_rate_limiting():
    state = {}
    assert guardian.alert_due(state, "swap", NOW, dt.timedelta(hours=1))
    guardian.record_alert(state, "swap", NOW)
    assert not guardian.alert_due(state, "swap", NOW + dt.timedelta(minutes=59), dt.timedelta(hours=1))
    assert guardian.alert_due(state, "swap", NOW + dt.timedelta(hours=1), dt.timedelta(hours=1))
    assert guardian.alert_due(state, "disk", NOW, dt.timedelta(hours=1))


def test_run_sends_one_alert_per_condition_per_hour(tmp_path, monkeypatch):
    monkeypatch.setattr(
        guardian, "measure", lambda now: fake_metrics(30 * GIB, swap_used=9.5 * GIB)
    )
    sent = []
    monkeypatch.setattr(guardian, "notify", lambda message: sent.append(message))
    config = make_config(tmp_path)

    guardian.run(config, now=NOW)
    assert len(sent) == 1 and "swap" in sent[0]
    guardian.run(config, now=NOW + dt.timedelta(minutes=30))
    assert len(sent) == 1
    guardian.run(config, now=NOW + dt.timedelta(hours=1, minutes=1))
    assert len(sent) == 2

    state = json.loads((tmp_path / "state" / "alerts.json").read_text())
    assert "swap" in state


def test_run_writes_sample_and_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(guardian, "measure", lambda now: fake_metrics(30 * GIB))
    config = make_config(tmp_path)
    guardian.run(config, now=NOW)
    samples = tmp_path / "state" / "samples.jsonl"
    lines = samples.read_text().splitlines()
    assert len(lines) == 1
    sample = json.loads(lines[0])
    assert sample["disk_free_bytes"] == 30 * GIB
    assert sample["cleanup"]["gate_open"] is False

    for _ in range(10):
        guardian.append_sample(tmp_path / "state", {"data": "x" * 100}, max_bytes=200)
    assert (tmp_path / "state" / "samples.jsonl.1").exists()


def test_evaluate_alert_conditions():
    config = make_config(Path("/nonexistent"))
    conditions = guardian.evaluate_alert_conditions(10 * GIB, 9.5 * GIB, 10 * GIB, config)
    assert [name for name, _ in conditions] == ["disk", "swap"]
    assert guardian.evaluate_alert_conditions(20 * GIB, 1 * GIB, 10 * GIB, config) == []


def test_render_mentions_mode_and_reclaim(tmp_path, monkeypatch):
    log = tmp_path / "big.log"
    log.write_bytes(b"x" * 2048)
    monkeypatch.setattr(guardian, "measure", lambda now: fake_metrics(10 * GIB))
    config = make_config(
        tmp_path, log_patterns=(str(log),), log_size_limit=1000, dry_run=True
    )
    text = guardian.render(guardian.run(config, now=NOW))
    assert "DRY RUN" in text
    assert "would rotate-log" in text
    assert "free after cleanup" in text
