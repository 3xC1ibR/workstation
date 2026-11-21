#!/usr/bin/env python3
"""Export conversation metadata from the local Messages database."""
import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
CHICAGO = ZoneInfo("America/Chicago")
OUTPUT = Path(".local/state/replies-owed/replies_owed.json")

# Normalize before ordering: migrated threads can contain both date units.
# In descending time order only the leading run before the first reply is owed.
REPLIES_QUERY = """
WITH events AS (
    SELECT j.chat_id, m.ROWID AS message_id, m.is_from_me,
           CASE WHEN m.date BETWEEN -2147483648 AND 4294967295
                THEN m.date * 1000000000 ELSE m.date END AS date_ns
    FROM chat_message_join AS j JOIN message AS m ON m.ROWID = j.message_id
    WHERE m.associated_message_type = 0 AND m.item_type = 0
      AND m.date IS NOT NULL AND m.is_from_me IN (0, 1)
), history AS (
    SELECT *, ROW_NUMBER() OVER recent AS position,
           SUM(is_from_me) OVER recent AS replies
    FROM events
    WINDOW recent AS (PARTITION BY chat_id ORDER BY date_ns DESC, message_id DESC
                      ROWS UNBOUNDED PRECEDING)
), owed AS (
    SELECT chat_id, COUNT(*) AS inbound_count,
           MAX(CASE WHEN position = 1 THEN message_id END) AS latest_id,
           MAX(date_ns) AS latest_ns
    FROM history WHERE replies = 0 GROUP BY chat_id
), membership AS (
    SELECT chat_id, COUNT(DISTINCT handle_id) AS members
    FROM chat_handle_join GROUP BY chat_id
)
SELECT h.id AS sender, c.chat_identifier, c.group_id,
       (c.style IN (2, 43) OR c.guid LIKE '%;+;%'
        OR COALESCE(membership.members, 0) > 1) AS is_group,
       COALESCE(NULLIF(m.service, ''), c.service_name) AS service,
       owed.latest_ns, owed.inbound_count
FROM owed JOIN message AS m ON m.ROWID = owed.latest_id
JOIN chat AS c ON c.ROWID = owed.chat_id
LEFT JOIN handle AS h ON h.ROWID = m.handle_id
LEFT JOIN membership ON membership.chat_id = c.ROWID
ORDER BY owed.latest_ns, c.ROWID
"""


def open_database(path):
    # Preserve EPERM/EACCES when SQLite would collapse them into CANTOPEN.
    with path.open("rb"):
        pass
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA trusted_schema = OFF")
    return connection


def contact_key(value):
    if not value:
        return ""
    if "@" in value:
        return value.strip().casefold()
    digits = re.sub(r"[\s()+.\-]", "", value)
    if digits.isascii() and digits.isdigit():
        # Local ten-digit numbers on this US workstation use country code 1.
        if len(digits) == 10 and not value.lstrip().startswith("+"):
            return "1" + digits
        return digits
    return value


def contact_names(directory, handles):
    matches = defaultdict(set)
    if not handles:
        return {}
    databases = [directory / "AddressBook-v22.abcddb"]
    try:
        databases.extend(directory.glob("Sources/*/AddressBook-v22.abcddb"))
    except OSError:
        pass  # The local database can still be available without the account directory.
    for path in databases:
        try:
            with closing(open_database(path)) as connection:
                connection.create_function("wanted", 1, lambda value: contact_key(value) in handles)
                for table, column in (("ZABCDPHONENUMBER", "ZFULLNUMBER"),
                                      ("ZABCDEMAILADDRESS", "ZADDRESS")):
                    rows = connection.execute(f"""
                        SELECT a.{column}, r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION
                        FROM {table} AS a JOIN ZABCDRECORD AS r ON r.Z_PK = a.ZOWNER
                        WHERE wanted(a.{column})
                    """)
                    for address, first, last, organization in rows:
                        name = " ".join(part for part in (first, last) if part) or organization
                        if name:
                            matches[contact_key(address)].add(name)
        except (OSError, sqlite3.Error):
            continue
    return {key: next(iter(names)) for key, names in matches.items() if len(names) == 1}


def read_replies(home, now, include_groups):
    entries = []
    with closing(open_database(home / "Library/Messages/chat.db")) as connection:
        for row in connection.execute(REPLIES_QUERY):
            group = bool(row["is_group"])
            if group and not include_groups:
                continue
            handle = row["sender"] or row["chat_identifier"]
            if group:
                target = quote(row["group_id"] or row["chat_identifier"], safe="")
                url = "sms://open?groupid=" + target
            else:
                target = quote(row["chat_identifier"] or handle, safe="")
                url = "sms://open?addresses=" + target
            received = APPLE_EPOCH + timedelta(microseconds=row["latest_ns"] // 1000)
            entries.append({
                "handle": handle,
                "service": row["service"],
                "is_group": group,
                "last_inbound_at": received.astimezone(CHICAGO).isoformat(),
                "waiting_days": max(0, (now.astimezone(timezone.utc) - received).days),
                "inbound_count_since_last_reply": row["inbound_count"],
                "open_url": url,
            })
    keys = {contact_key(entry["handle"]) for entry in entries}
    names = contact_names(home / "Library/Application Support/AddressBook", keys)
    for entry in entries:
        entry["display_name"] = names.get(contact_key(entry["handle"]))
    return entries


def write_summary(path, summary):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8",
                                     delete=False) as output:
        pending = Path(output.name)
        try:
            json.dump(summary, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
            os.replace(pending, path)
        finally:
            pending.unlink(missing_ok=True)


def export(home, now, include_groups=False):
    entries = []
    status = "ok"
    try:
        entries = read_replies(home, now, include_groups)
    except PermissionError:
        status = "permission_denied"
    except sqlite3.Error as error:
        # Apple's Python 3.9 has no sqlite_errorcode attribute.
        denied = ("authorization denied", "not authorized", "permission denied",
                  "operation not permitted")
        detail = str(error).lower()
        status = "permission_denied" if any(term in detail for term in denied) else "error"
    except (OSError, TypeError, ValueError, OverflowError):
        status = "error"
    write_summary(home / OUTPUT, {
        "generated_at": now.astimezone(CHICAGO).isoformat(),
        "source_status": status,
        "replies_owed": entries,
    })
    return 0 if status == "ok" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-groups", action="store_true")
    options = parser.parse_args()
    return export(Path.home(), datetime.now(timezone.utc), options.include_groups)


if __name__ == "__main__":
    sys.exit(main())
