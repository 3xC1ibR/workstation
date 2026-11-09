from contextlib import closing
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load("backup_agent_data")
retention = load("configure_agent_retention")


class AgentDataBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "native sessions"
        self.source.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()

    def test_online_snapshot_includes_uncheckpointed_wal(self):
        path = self.source / "history.sqlite3"
        with closing(sqlite3.connect(path)) as source:
            source.execute("PRAGMA journal_mode=WAL")
            source.execute("CREATE TABLE events (body TEXT)")
            source.execute("INSERT INTO events VALUES ('uncheckpointed')")
            source.commit()
            roots, manifest = backup.prepare([self.source, self.root / "missing"], self.state)
            with closing(sqlite3.connect(manifest["databases"][0]["snapshot"])) as restored:
                self.assertEqual(restored.execute("SELECT body FROM events").fetchone(), ("uncheckpointed",))
        self.assertIn(str(path) + "-wal", (self.state / "exclusions.txt").read_text())
        self.assertEqual(manifest["missing_sources"], [str(self.root / "missing")])

    def test_snapshot_error_aborts_instead_of_reporting_success(self):
        path = self.source / "broken.sqlite"
        path.write_bytes(b"SQLite format 3\x00" + b"invalid data")
        with self.assertRaises(sqlite3.DatabaseError):
            backup.prepare([self.source], self.state)
        self.assertFalse((self.state / "manifest.json").exists())

    def test_staging_inside_source_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "outside"):
            backup.prepare([self.root], self.state)

    def test_interrupted_destination_wal_is_removed_before_restarting(self):
        source = self.source / "history.sqlite"
        with closing(sqlite3.connect(source)) as database:
            database.execute("CREATE TABLE events (body TEXT)")
            database.execute("INSERT INTO events VALUES ('current source')")
            database.commit()
        destination = self.state / "history.sqlite"
        pending = destination.with_name(destination.name + ".pending")
        subprocess.run([sys.executable, "-c",
            "import os,sqlite3,sys; d=sqlite3.connect(sys.argv[1]); "
            "d.execute('PRAGMA journal_mode=WAL'); d.execute('CREATE TABLE stale (body TEXT)'); "
            "d.commit(); os._exit(0)", str(pending)], check=True)
        self.assertTrue(Path(str(pending) + "-wal").exists())
        backup.snapshot_database(source, destination)
        with closing(sqlite3.connect(destination)) as database:
            self.assertEqual(database.execute("SELECT body FROM events").fetchone(), ("current source",))
            self.assertEqual(database.execute("SELECT count(*) FROM sqlite_master WHERE name='stale'").fetchone(), (0,))

    def test_retention_preserves_unrelated_settings_and_toml_sections(self):
        home = self.root / "home"
        for name, text in {
            ".claude/settings.json": '{"hooks": {"Stop": [1]}, "cleanupPeriodDays": 30}',
            ".config/muse/settings.json": '{"schema_version": 1, "session_retention_days": 5}',
            ".gemini/settings.json": '{"security": {"auth": {}}, "general": {"sessionRetention": {"enabled": true}}}',
            ".codex/config.toml": 'model = "example"\n[history]\npersistence = "none"\nmax_bytes = 12\n[profiles.test]\nmodel = "other"\n',
        }.items():
            path = home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        retention.configure(home, self.state)
        self.assertEqual(json.loads((home / ".claude/settings.json").read_text())["hooks"], {"Stop": [1]})
        self.assertEqual(json.loads((home / ".claude/settings.json").read_text())["cleanupPeriodDays"], 36500)
        self.assertNotIn("session_retention_days", json.loads((home / ".config/muse/settings.json").read_text()))
        self.assertFalse(json.loads((home / ".gemini/settings.json").read_text())["general"]["sessionRetention"]["enabled"])
        parsed = retention.tomllib.loads((home / ".codex/config.toml").read_text())
        self.assertEqual(parsed["history"], {"persistence": "save-all"})
        self.assertEqual(parsed["profiles"]["test"]["model"], "other")
        self.assertEqual(retention.configure(home, self.state), [])

    @unittest.skipUnless(shutil.which("restic"), "Restic is required for restore verification")
    def test_real_restic_restore_and_previous_snapshot_survive_source_deletion(self):
        transcript = self.source / "session.jsonl"
        transcript.write_text('{"body":"original transcript"}\n')
        (self.source / ".hidden-blob").write_bytes(b"large tool result" * 1000)
        (self.source / "link").symlink_to(".hidden-blob")
        with closing(sqlite3.connect(self.source / "session.db")) as database:
            database.execute("CREATE TABLE events (body TEXT)")
            database.execute("INSERT INTO events VALUES ('saved event')")
            database.commit()
        password = self.root / "password"
        password.write_text("test encryption password")
        config = {"repository": str(self.root / "repository"), "password_file": str(password),
                  "restic": shutil.which("restic"), "sources": [str(self.source)]}
        backup.run(config, self.state)
        environment = backup.restic_environment(config, self.state)
        snapshots = json.loads(subprocess.check_output([config["restic"], "snapshots", "--json"], env=environment))
        first = snapshots[0]["id"]
        transcript.unlink()
        backup.run(config, self.state)
        target = self.root / "restore"
        subprocess.run([config["restic"], "restore", first, "--target", str(target)],
                       env=environment, check=True, capture_output=True)
        restored_source = target / self.source.relative_to("/")
        self.assertEqual((restored_source / "session.jsonl").read_text(), '{"body":"original transcript"}\n')
        self.assertTrue((restored_source / "link").is_symlink())
        self.assertEqual((restored_source / ".hidden-blob").read_bytes(), b"large tool result" * 1000)
        self.assertFalse((restored_source / "session.db").exists())
        restored_database = next((target / self.state.relative_to("/") / "sqlite").rglob("session.db"))
        with closing(sqlite3.connect(restored_database)) as database:
            self.assertEqual(database.execute("SELECT body FROM events").fetchone(), ("saved event",))
        subprocess.run([config["restic"], "check", "--read-data"], env=environment, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
