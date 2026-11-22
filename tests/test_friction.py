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


def resolution_arguments(*record_ids, disposition="fixed", reference="abc1234"):
    return ["--resolve", *record_ids, "--disposition", disposition, "--reference", reference]


def test_new_records_declare_report_kind(tmp_path):
    store = tmp_path / "records.jsonl"

    assert run_command(["The fixture path was stale."], store, tmp_path).returncode == 0

    assert json.loads(store.read_text())["kind"] == "report"


def test_resolution_hides_records_from_default_listing(tmp_path):
    store = tmp_path / "records.jsonl"
    friction.append_record({"id": "frc_a", "project": "stoic", "text": "first"}, store)
    friction.append_record({"id": "frc_b", "project": "stoic", "text": "second"}, store)

    completed = run_command(
        [*resolution_arguments("frc_a", reference="stoic-12"), "--note", "Fixed  at the cause."],
        store,
        tmp_path,
        {"AGENT_COORD_SESSION_ID": "triage-1"},
    )

    assert completed.returncode == 0, completed.stderr
    assert "Resolved 1 records as fixed" in completed.stdout
    resolution = json.loads(store.read_text().splitlines()[-1])
    assert resolution["kind"] == "resolution"
    assert resolution["resolves"] == ["frc_a"]
    assert resolution["reference"] == "stoic-12"
    assert resolution["note"] == "Fixed at the cause."
    assert resolution["session_id"] == "triage-1"
    default = friction.list_records(store, None, None, "markdown")
    assert "frc_b" in default and "frc_a" not in default
    assert "## stoic (1)" in default
    complete = friction.list_records(store, None, None, "markdown", include_resolved=True)
    assert "frc_a [unclassified, unknown] (resolved fixed: stoic-12) first" in complete


def test_listing_ignores_resolution_entries_and_reports_latest_resolution(tmp_path):
    store = tmp_path / "records.jsonl"
    friction.append_record({"id": "frc_a", "text": "legacy record without kind"}, store)
    assert run_command(resolution_arguments("frc_a", disposition="stale", reference="r1"), store, tmp_path).returncode == 0
    assert run_command(resolution_arguments("frc_a", disposition="fixed", reference="r2"), store, tmp_path).returncode == 0

    lines = friction.list_records(store, None, None, "jsonl", include_resolved=True).splitlines()

    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["id"] == "frc_a"
    assert record["resolution"]["disposition"] == "fixed"
    assert record["resolution"]["reference"] == "r2"
    assert friction.list_records(store, None, None, "jsonl") == ""


def test_resolution_reads_identifiers_from_standard_input(tmp_path):
    store = tmp_path / "records.jsonl"
    for record_id in ("frc_a", "frc_b", "frc_c"):
        friction.append_record({"id": record_id, "text": record_id}, store)

    completed = run_command(
        resolution_arguments("-", disposition="duplicate", reference="frc_c"),
        store,
        tmp_path,
        stdin="frc_a\nfrc_b frc_a\n",
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(store.read_text().splitlines()[-1])["resolves"] == ["frc_a", "frc_b"]


def test_resolution_rejects_unknown_identifiers_and_missing_evidence(tmp_path):
    store = tmp_path / "records.jsonl"
    friction.append_record({"id": "frc_a", "text": "a"}, store)
    before = store.read_text()

    unknown = run_command(resolution_arguments("frc_a", "frc_missing"), store, tmp_path)
    missing_reference = run_command(["--resolve", "frc_a", "--disposition", "fixed"], store, tmp_path)
    blank_reference = run_command(resolution_arguments("frc_a", reference="  "), store, tmp_path)
    resolution_identifier = run_command(resolution_arguments("frc_a"), store, tmp_path)
    resolution_id = json.loads(store.read_text().splitlines()[-1])["id"]
    after_valid = store.read_text()
    resolves_resolution = run_command(resolution_arguments(resolution_id), store, tmp_path)

    assert unknown.returncode == 2 and "frc_missing" in unknown.stderr
    assert missing_reference.returncode == 2
    assert blank_reference.returncode == 2
    assert resolution_identifier.returncode == 0
    assert after_valid.startswith(before) and len(after_valid.splitlines()) == 2
    assert resolves_resolution.returncode == 2
    assert store.read_text() == after_valid


def test_list_filters_by_scope(tmp_path):
    store = tmp_path / "records.jsonl"
    friction.append_record({"id": "frc_a", "scope": "harness", "text": "a"}, store)
    friction.append_record({"id": "frc_b", "scope": "repository", "text": "b"}, store)

    listing = friction.list_records(store, None, None, "markdown", scope="repository")

    assert "frc_b" in listing and "frc_a" not in listing
