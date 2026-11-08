import importlib.util
import json
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "friction.py"
spec = importlib.util.spec_from_file_location("friction", SCRIPT)
friction = importlib.util.module_from_spec(spec)
sys.modules["friction"] = friction
spec.loader.exec_module(friction)


def run_command(arguments, store, cwd, environment=None, stdin=None):
    env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "FRICTION_STORE": str(store)}
    env.update(environment or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def initialize_repository(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "initial"],
        cwd=path,
        check=True,
    )


def test_records_one_line_with_automatic_context(tmp_path):
    repository = tmp_path / "sample"
    initialize_repository(repository)
    store = tmp_path / "state" / "records.jsonl"

    completed = run_command(
        ["While running tests,   the fixture\npath was stale.", "--scope", "repository"],
        store,
        repository,
        {"AGENT_COORD_CLIENT": "codex", "AGENT_COORD_SESSION_ID": "session-1"},
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("Recorded frc_")
    record = json.loads(store.read_text())
    assert record["text"] == "While running tests, the fixture path was stale."
    assert record["scope"] == "repository"
    assert record["project"] == "sample"
    assert record["branch"] == "main"
    assert record["commit"]
    assert record["provider"] == "codex"
    assert record["session_id"] == "session-1"
    assert stat.S_IMODE(store.stat().st_mode) == 0o600


def test_worktree_maps_to_main_repository(tmp_path):
    repository = tmp_path / "main-checkout"
    initialize_repository(repository)
    worktree = tmp_path / "feature-checkout"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "feature", str(worktree)], cwd=repository, check=True)

    context = friction.repository_context(worktree)

    assert context["project"] == "main-checkout"
    assert Path(context["repository_root"]).resolve() == repository.resolve()
    assert Path(context["worktree_root"]).resolve() == worktree.resolve()
    assert context["branch"] == "feature"


def test_outside_repository_uses_directory_name(tmp_path):
    context = friction.repository_context(tmp_path)

    assert context["project"] == tmp_path.name
    assert context["repository_root"] is None


def test_provider_detection_from_native_variables():
    assert friction.agent_context({"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "c1"}) == {
        "provider": "claude",
        "session_id": "c1",
    }
    assert friction.agent_context({"CODEX_THREAD_ID": "t1"}) == {"provider": "codex", "session_id": "t1"}
    assert friction.agent_context({}) == {"provider": "unknown", "session_id": None}


def test_reads_standard_input_for_text_with_quotes(tmp_path):
    store = tmp_path / "records.jsonl"

    completed = run_command(["-"], store, tmp_path, stdin="The `bd` command's output was misleading.\n")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(store.read_text())["text"] == "The `bd` command's output was misleading."


def test_rejects_empty_and_oversized_text(tmp_path):
    store = tmp_path / "records.jsonl"

    assert run_command(["   "], store, tmp_path).returncode == 2
    assert run_command(["x" * (friction.MAXIMUM_TEXT_LENGTH + 1)], store, tmp_path).returncode == 2
    assert not store.exists()


def test_concurrent_appends_remain_whole_lines(tmp_path):
    store = tmp_path / "records.jsonl"

    def record(index):
        friction.append_record({"id": index, "text": "y" * 1000}, store)

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(record, range(200)))

    lines = store.read_text().splitlines()
    assert len(lines) == 200
    assert sorted(json.loads(line)["id"] for line in lines) == list(range(200))


def test_list_groups_by_project_and_filters(tmp_path):
    store = tmp_path / "records.jsonl"
    friction.append_record({"project": "rig", "recorded_at": "2026-11-01T00:00:00+00:00", "text": "a"}, store)
    friction.append_record({"project": "rig", "recorded_at": "2026-11-03T00:00:00+00:00", "text": "b"}, store)
    friction.append_record({"project": "forge", "recorded_at": "2026-11-02T00:00:00+00:00", "text": "c"}, store)

    full = friction.list_records(store, None, None, "markdown")
    assert full.index("## rig (2)") < full.index("## forge (1)")
    assert full.index("] b") < full.index("] a")
    assert "] c" not in friction.list_records(store, "rig", None, "markdown")
    assert "] a" not in friction.list_records(store, None, "2026-11-02", "markdown")
