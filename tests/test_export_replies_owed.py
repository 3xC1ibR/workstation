import datetime as dt
import importlib.util
import json
import sqlite3
import stat
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_replies_owed.py"
spec = importlib.util.spec_from_file_location("export_replies_owed", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

NOW = dt.datetime(2026, 11, 21, 19, tzinfo=dt.timezone.utc)
SECONDS = int((NOW - exporter.APPLE_EPOCH).total_seconds())
DAY = 86400
BILLION = 1_000_000_000
PHONE = "+13125550100"
EMAIL = "a+b@example.test"


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "Library/Messages/chat.db"
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE handle (id TEXT);
            CREATE TABLE chat (chat_identifier, group_id, style, guid, service_name);
            CREATE TABLE message (date INTEGER, is_from_me, associated_message_type,
                                  handle_id, service, item_type DEFAULT 0, text, attributedBody);
            CREATE TABLE chat_handle_join (chat_id, handle_id);
            CREATE TABLE chat_message_join (chat_id, message_id);
            INSERT INTO handle VALUES ('+13125550100'), ('a+b@example.test');
            INSERT INTO chat VALUES
                ('+13125550100', NULL, 45, 'SMS;-;+13125550100', 'SMS'),
                ('a+b@example.test', NULL, 45, 'iMessage;-;a+b@example.test', 'iMessage'),
                ('chat123', 'group-123', 43, 'iMessage;+;chat123', 'iMessage');
            INSERT INTO chat_handle_join VALUES (1,1), (2,2), (3,1), (3,2);
        """)
        yield conn


def message(conn, chat, date, outgoing=0, association=0, item_type=0):
    sender = 2 if chat == 2 else 1
    row = conn.execute("""
        INSERT INTO message(date, is_from_me, associated_message_type, handle_id,
                            item_type, text, attributedBody)
        VALUES (?, ?, ?, ?, ?, 'PRIVATE TEXT', 'PRIVATE BODY')
    """, (date, outgoing, association, sender, item_type))
    conn.execute("INSERT INTO chat_message_join VALUES (?,?)", (chat, row.lastrowid))
    conn.commit()


def summary(home):
    return json.loads((home / exporter.OUTPUT).read_text())


def test_replies_in_live_wal_and_mixed_date_units(tmp_path, database, monkeypatch):
    # Insertion order differs from event order. Raw dates cannot be compared.
    message(database, 1, (SECONDS - DAY) * BILLION, outgoing=1)
    message(database, 1, SECONDS, outgoing=0, association=2001)
    message(database, 2, (SECONDS - 12 * DAY) * BILLION, outgoing=1)
    message(database, 2, (SECONDS - 7 * DAY) * BILLION)
    message(database, 2, SECONDS - 6 * DAY, outgoing=1)
    message(database, 2, SECONDS - 3 * DAY)
    message(database, 2, (SECONDS - 2 * DAY) * BILLION + 123456789)
    message(database, 2, SECONDS, outgoing=1, association=3000)
    message(database, 2, SECONDS, outgoing=1, item_type=2)
    assert (tmp_path / "Library/Messages/chat.db-wal").stat().st_size > 0

    original_open = exporter.open_database

    def guard_columns(path):
        conn = original_open(path)

        def authorize(action, table, column, schema, view):
            if action == sqlite3.SQLITE_READ and table == "message":
                if column not in {"ROWID", "date", "is_from_me", "associated_message_type",
                                  "handle_id", "service", "item_type"}:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorize)
        return conn

    monkeypatch.setattr(exporter, "open_database", guard_columns)
    assert exporter.export(tmp_path, NOW) == 0
    report = summary(tmp_path)
    assert report == {
        "generated_at": "2026-11-21T13:00:00-06:00", "source_status": "ok",
        "replies_owed": [{
            "handle": EMAIL, "is_group": False, "display_name": None, "service": "iMessage",
            "last_outbound_at": "2026-11-15T13:00:00-06:00",
            "last_inbound_at": "2026-11-19T13:00:00.123456-06:00",
            "waiting_days": 1, "inbound_count_since_last_reply": 2,
            "open_url": "sms://open?addresses=a%2Bb%40example.test",
        }],
    }
    assert stat.S_IMODE((tmp_path / exporter.OUTPUT).stat().st_mode) == 0o600


def test_equal_timestamps_and_outbound_last(tmp_path, database):
    message(database, 1, SECONDS)
    message(database, 1, SECONDS, outgoing=1)
    message(database, 1, SECONDS + 1, association=2000)
    assert exporter.export(tmp_path, NOW) == 0
    assert summary(tmp_path)["replies_owed"] == []
    message(database, 1, SECONDS)
    assert exporter.export(tmp_path, NOW) == 0
    entry, = summary(tmp_path)["replies_owed"]
    assert entry["inbound_count_since_last_reply"] == 1
    assert entry["last_inbound_at"] == "2026-11-21T13:00:00-06:00"


def test_groups_opt_in_and_shortest_wait_first(tmp_path, database):
    message(database, 1, SECONDS - 12 * DAY, outgoing=1)
    message(database, 3, SECONDS - 12 * DAY, outgoing=1)
    message(database, 3, SECONDS - 9 * DAY)
    message(database, 3, SECONDS - 8 * DAY)
    message(database, 1, SECONDS)
    assert exporter.export(tmp_path, NOW) == 0
    assert [entry["is_group"] for entry in summary(tmp_path)["replies_owed"]] == [False]
    assert exporter.export(tmp_path, NOW, include_groups=True) == 0
    direct, group = summary(tmp_path)["replies_owed"]
    assert group["inbound_count_since_last_reply"] == 2
    assert group["handle"] == PHONE
    assert group["is_group"] and group["open_url"] == "sms://open?groupid=group-123"
    assert direct["open_url"] == "sms://open?addresses=%2B13125550100"
    database.execute("DELETE FROM chat_handle_join WHERE chat_id=3 AND handle_id=2")
    database.commit()
    assert exporter.export(tmp_path, NOW) == 0
    assert summary(tmp_path)["replies_owed"] == [direct]


def test_never_replied_is_opt_in_and_reactions_do_not_count(tmp_path, database):
    message(database, 1, SECONDS - DAY, outgoing=1, association=2000)
    message(database, 1, SECONDS)
    assert exporter.export(tmp_path, NOW) == 0
    assert summary(tmp_path)["replies_owed"] == []
    assert exporter.export(tmp_path, NOW, include_never_replied=True) == 0
    entry, = summary(tmp_path)["replies_owed"]
    assert entry["last_outbound_at"] is None
    assert entry["inbound_count_since_last_reply"] == 1


@pytest.mark.parametrize(("handle", "short"), [
    ("1", True), ("012345", True), ("1234567", False), ("+12345", False), ("a12345", False),
])
def test_short_code_filter_is_independent_of_conversation_history(tmp_path, database, handle, short):
    database.execute("UPDATE handle SET id=? WHERE ROWID=1", (handle,))
    message(database, 1, SECONDS - DAY, outgoing=1)
    message(database, 1, SECONDS)
    assert exporter.export(tmp_path, NOW, include_never_replied=True) == 0
    assert len(summary(tmp_path)["replies_owed"]) == (0 if short else 1)
    assert exporter.export(tmp_path, NOW, include_short_codes=True) == 0
    entry, = summary(tmp_path)["replies_owed"]
    assert entry["handle"] == handle


def test_age_cutoff_uses_latest_inbound_and_all_time_outbound_history(tmp_path, database):
    for chat in (1, 2):
        message(database, chat, SECONDS - 365 * DAY, outgoing=1)
    cutoff = (SECONDS - 180 * DAY) * BILLION
    message(database, 1, cutoff)
    message(database, 2, cutoff - 1)
    assert exporter.export(tmp_path, NOW) == 0
    entry, = summary(tmp_path)["replies_owed"]
    assert entry["handle"] == PHONE
    assert entry["waiting_days"] == 180
    assert entry["last_outbound_at"] == "2025-11-21T13:00:00-06:00"
    assert exporter.export(tmp_path, NOW, max_age_days=179) == 0
    assert summary(tmp_path)["replies_owed"] == []
    assert exporter.export(tmp_path, NOW, max_age_days=0) == 0
    assert [row["handle"] for row in summary(tmp_path)["replies_owed"]] == [PHONE, EMAIL]


def test_optional_contact_names(tmp_path, database):
    directory = tmp_path / "Library/Application Support/AddressBook/Sources/account"
    directory.mkdir(parents=True)
    with closing(sqlite3.connect(directory / "AddressBook-v22.abcddb")) as contacts:
        contacts.executescript("""
            CREATE TABLE ZABCDRECORD (Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION);
            CREATE TABLE ZABCDPHONENUMBER (ZOWNER, ZFULLNUMBER);
            CREATE TABLE ZABCDEMAILADDRESS (ZOWNER, ZADDRESS);
            INSERT INTO ZABCDRECORD VALUES (1, 'Taylor', 'Example', NULL),
                                           (2, NULL, NULL, 'Example Co.');
            INSERT INTO ZABCDPHONENUMBER VALUES (1, '(312) 555-0100');
            INSERT INTO ZABCDEMAILADDRESS VALUES (2, 'A+B@EXAMPLE.TEST');
        """)
    message(database, 1, SECONDS - 2, outgoing=1)
    message(database, 2, SECONDS - 2, outgoing=1)
    message(database, 1, SECONDS)
    message(database, 2, SECONDS)
    assert exporter.export(tmp_path, NOW) == 0
    assert [row["display_name"] for row in summary(tmp_path)["replies_owed"]] == [
        "Taylor Example", "Example Co."]


@pytest.mark.parametrize("failure", [PermissionError(), sqlite3.DatabaseError("authorization denied")])
def test_permission_failure_replaces_previous_success(tmp_path, database, monkeypatch, failure):
    message(database, 1, SECONDS - DAY, outgoing=1)
    message(database, 1, SECONDS)
    assert exporter.export(tmp_path, NOW) == 0

    assert len(summary(tmp_path)["replies_owed"]) == 1

    def denied(path):
        raise failure

    monkeypatch.setattr(exporter, "open_database", denied)
    assert exporter.export(tmp_path, NOW) == 1
    assert summary(tmp_path)["source_status"] == "permission_denied"
    assert summary(tmp_path)["replies_owed"] == []


def test_missing_database_reports_error_without_creating_source(tmp_path):
    assert exporter.export(tmp_path, NOW) == 1
    assert summary(tmp_path)["source_status"] == "error"
    assert not (tmp_path / "Library/Messages/chat.db").exists()


def test_interrupted_publication_preserves_previous_report(tmp_path, database, monkeypatch):
    assert exporter.export(tmp_path, NOW) == 0
    output = tmp_path / exporter.OUTPUT
    previous = output.read_bytes()
    message(database, 1, SECONDS)

    def fail_replace(source, destination):
        raise OSError("interrupted publication")

    monkeypatch.setattr(exporter.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted publication"):
        exporter.export(tmp_path, NOW)
    assert output.read_bytes() == previous
    assert list(output.parent.iterdir()) == [output]


def test_signed_bundle_interface(tmp_path, monkeypatch):
    if not Path("/Library/Developer/CommandLineTools/usr/bin/python3").is_file():
        pytest.skip("requires macOS Command Line Tools")
    monkeypatch.setenv("HOME", str(tmp_path))
    subprocess.run([SCRIPT.with_name("build_replies_owed_app.sh")], check=True)
    bundle = tmp_path / "Applications/RepliesOwedExporter.app"
    subprocess.run(["codesign", "--verify", "--strict", bundle], check=True)
    launcher = bundle / "Contents/MacOS/RepliesOwedExporter"
    flags = ["--include-groups", "--include-never-replied", "--include-short-codes"]
    result = subprocess.run([launcher, *flags, "--max-age-days", "180", "--help"],
                            check=True, capture_output=True, text=True)
    assert all(option in result.stdout for option in [*flags, "--max-age-days"])
    subprocess.run([launcher, "--max-age-days=0", "--help"], check=True)
    for invalid in (["--database"], ["--max-age-days"], ["--max-age-days", "-1"],
                    ["--max-age-days=unknown"]):
        assert subprocess.run([launcher, *invalid]).returncode == 64
