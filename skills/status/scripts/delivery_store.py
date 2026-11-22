"""Proactive deliveries: unrequested work an agent hands to the user, and his responses.

Each published version is an immutable directory holding delivery.json, an
optional Markdown document, retained text attachments, and an optional
interactive document. Versions sharing a series are one living delivery: a
stable key, or a delivery named by a later version that replaces it; a
delivery published without either is the only version of its own series. The
user's responses (read, accepted, dismissed, discussed) belong to the series
and record the version they were given on. They are stored separately with
their times, so agents can read them without a running viewer.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import tempfile

from document_state import DocumentStates
import interactive_documents
from status_store import IDENTIFIER, ResponseConflict, StatusError, moment, read_text, write_json

DOCUMENT_LIMIT = 2 * 1024 * 1024
ATTACHMENT_LIMIT = 2 * 1024 * 1024
ATTACHMENT_COUNT = 12
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".log", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".py", ".sh", ".sql", ".diff", ".patch"}
THREAD_LINK = re.compile(r"agentcoord://thread/[A-Za-z0-9_-]{1,128}\Z")
LINK_TARGET = re.compile(r"(https?://[^\s]+|agentcoord://[^\s]+|/[^\0]*)\Z")
ACTIONS = {"read", "accept", "dismiss", "discuss", "reopen"}
RECOMMENDED = "recommended_default"
DELIVERY_KEY = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*\Z")           # the same rule as an operation key
STATE_FIELDS = {"read_at", "read_version", "response", "discussed_at", "history"}
EARLIER_STATE_FIELDS = STATE_FIELDS - {"read_version"}            # records written before deliveries had versions


def series_identity(manifest):
    """Stable identity shared by every version of one delivery.

    A key identifies the series wherever it is published. A version published
    with --replaces records the series it joined. Any other delivery is its own
    series, so records and addresses from before versions existed are unchanged.
    """
    if manifest.get("key"):
        return hashlib.sha256(json.dumps(["delivery", manifest["key"]], separators=(",", ":")).encode()).hexdigest()
    return manifest.get("series") or manifest["id"]


def text(value, label, limit, *, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be nonempty text of at most {limit} characters")
    return value.strip()


def validate(document):
    """Check a delivery document; unknown fields are errors, never silent loss."""
    allowed = {"title", "summary", "recommended_default", "decision", "category", "links", "thread", "created_at"}
    if not isinstance(document, dict) or document.keys() - allowed:
        raise ValueError("A delivery accepts only: " + ", ".join(sorted(allowed)))
    text(document.get("title"), "title", 300, required=True)
    text(document.get("summary"), "summary", 2000, required=True)
    text(document.get("recommended_default"), "recommended_default", 1000)
    text(document.get("category"), "category", 60)
    decision = document.get("decision")
    if decision is not None:
        if not isinstance(decision, dict) or decision.keys() - {"question", "options"}:
            raise ValueError("decision accepts question and optional options")
        text(decision.get("question"), "decision.question", 1000, required=True)
        options = decision.get("options", [])
        if (not isinstance(options, list) or len(options) > 6 or len(set(map(str, options))) != len(options)
                or any(not isinstance(option, str) or not option.strip() or len(option) > 300 for option in options)
                or RECOMMENDED in options):
            raise ValueError("decision.options must be at most 6 unique nonempty choices of at most 300 characters")
    links = document.get("links", [])
    if not isinstance(links, list) or len(links) > 20:
        raise ValueError("links must be a list of at most 20 records")
    for link in links:
        if not isinstance(link, dict) or set(link) != {"label", "target"}:
            raise ValueError("Each link requires label and target")
        text(link["label"], "links.label", 200, required=True)
        if not isinstance(link["target"], str) or len(link["target"]) > 2000 or not LINK_TARGET.match(link["target"]):
            raise ValueError("links.target must be an http(s) address, an agentcoord:// link, or an absolute path")
    if "thread" in document and (not isinstance(document["thread"], str) or not THREAD_LINK.match(document["thread"])):
        raise ValueError("thread must be an agentcoord://thread/<id> link")
    if "created_at" in document:
        if not isinstance(document["created_at"], str):
            raise ValueError("created_at must be an ISO 8601 timestamp with a timezone")
        moment(document["created_at"])


def publish(document, *, workspace, agent=None, provider=None, thread_id=None, body=None, attachments=(), root,
            key=None, replaces=None, interactive_document=None, embed=None, public_prefix=None):
    """Retain a delivery and return its identifier. Publishing the same delivery again is idempotent.

    `key` makes this a version of the delivery with that stable key; `replaces`
    makes it a new version of an existing delivery that has no key. Publishing
    content identical to the series' latest version returns that version.
    """
    validate(document)
    if body is not None and (not isinstance(body, str) or not body.strip() or len(body.encode()) > DOCUMENT_LIMIT):
        raise ValueError("The delivery document must be nonempty text of at most 2 MB")
    if key is not None and replaces is not None:
        raise ValueError("Give a key or the delivery this one replaces, not both")
    if key is not None and (not isinstance(key, str) or not DELIVERY_KEY.fullmatch(key) or len(key) > 80):
        raise ValueError("A delivery key is 1-80 lowercase letters, digits, and single hyphens, such as thanksgiving-plan")
    interactive, retained = interactive_documents.source(interactive_document, embed, public_prefix)
    store, series = Deliveries(root), None
    if replaces is not None:
        try:
            replaced = store.manifest(replaces)
        except StatusError as error:
            raise ValueError("--replaces names a delivery identifier that is retained in this inbox") from error
        if replaced.get("key"):
            raise ValueError(f"That delivery is published under the key {replaced['key']}; publish its next version with that key")
        series = series_identity(replaced)
    files = []
    if len(attachments) > ATTACHMENT_COUNT:
        raise ValueError(f"At most {ATTACHMENT_COUNT} attachments are retained; link to larger collections instead")
    for path in map(Path, attachments):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise ValueError(f"{path.name}: only text attachments are retained ({', '.join(sorted(TEXT_SUFFIXES))})")
        content = path.read_bytes()
        if len(content) > ATTACHMENT_LIMIT or path.name in {name for name, _ in files}:
            raise ValueError(f"{path.name}: attachments must be unique names of at most 2 MB")
        files.append((path.name, content.decode("utf-8")))
    origin = {"workspace": str(workspace), "agent": agent or None, "provider": provider or None,
              "thread_id": thread_id or None, "host": socket.gethostname()}
    content = {"delivery": document, "origin": origin, "body": body, "attachments": files}
    if interactive:                                # each addition is absent from a plain delivery, whose identifier is unchanged
        content["interactive"] = {**interactive, "document": retained}
    if key:
        content["key"] = key
    if series:
        content["series"] = series
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    identifier = digest
    if key or series:
        versions = store.versions(series or series_identity({"key": key}))
        if versions and versions[0].get("content_digest") == digest:
            return versions[0]["id"]               # unchanged since the latest version: nothing new to read
        if versions:                               # the same content may return after a correction, as a new version
            identifier = hashlib.sha256(f"{digest}:{versions[0]['id']}".encode()).hexdigest()
    deliveries = Path(root) / "deliveries"
    deliveries.mkdir(parents=True, exist_ok=True)
    destination = deliveries / identifier
    if destination.exists():
        return identifier
    received = datetime.now(timezone.utc).isoformat()
    thread = document.get("thread") or (f"agentcoord://thread/{thread_id}" if thread_id and THREAD_LINK.match(f"agentcoord://thread/{thread_id}") else None)
    manifest = {"version": 1, "id": identifier, **document, "thread": thread,
                "created_at": document.get("created_at", received), "received_at": received, "origin": origin,
                "has_document": body is not None, "attachments": [name for name, _ in files]}
    if interactive:
        manifest["interactive"] = interactive
    if key or series:
        manifest.update({"key": key} if key else {"series": series}, content_digest=digest)
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=deliveries))
    try:
        (staging / "delivery.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
        if body is not None:
            (staging / "document.md").write_text(body, encoding="utf-8")
        if retained is not None:
            (staging / interactive_documents.DOCUMENT_NAME).write_text(retained, encoding="utf-8")
        (staging / "attachments").mkdir()
        for index, (_, content) in enumerate(files):
            (staging / "attachments" / str(index)).write_text(content, encoding="utf-8")
        try:
            staging.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return identifier


class Deliveries:
    def __init__(self, root):
        self.root = Path(root)
        self.states = DocumentStates(root)

    def _directory(self, identifier):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise StatusError("Invalid delivery identifier.")
        directory = self.root / "deliveries" / identifier
        if directory.is_symlink() or not directory.is_dir():
            raise StatusError("This delivery is unavailable.")
        return directory

    def manifest(self, identifier):
        """The stored record of one version."""
        directory = self._directory(identifier)
        try:
            manifest = json.loads(read_text(directory / "delivery.json", 256 * 1024))
            if manifest.get("version") != 1 or manifest.get("id") != identifier:
                raise ValueError("Unsupported delivery record")
            validate({key: value for key, value in manifest.items()
                      if key in {"title", "summary", "recommended_default", "decision", "category", "links", "created_at"}
                      and value is not None})
            moment(manifest["received_at"])
            if not isinstance(manifest["origin"], dict) or not isinstance(manifest["attachments"], list):
                raise ValueError("Invalid delivery origin")
            key, series = manifest.get("key"), manifest.get("series")
            if ((key is not None and (not isinstance(key, str) or not DELIVERY_KEY.fullmatch(key)))
                    or (series is not None and (key is not None or not isinstance(series, str) or not IDENTIFIER.fullmatch(series)))):
                raise ValueError("Invalid delivery series")
            manifest["interactive"] = interactive_documents.recorded(manifest)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise StatusError("The delivery record is invalid.") from error
        return manifest

    def _series(self):
        """Every readable version grouped by series, newest first, and the count of unreadable records."""
        groups, unreadable = {}, 0
        directory = self.root / "deliveries"
        if directory.exists():
            for entry in directory.iterdir():
                if not IDENTIFIER.fullmatch(entry.name):
                    continue
                try:
                    manifest = self.manifest(entry.name)
                    groups.setdefault(series_identity(manifest), []).append(manifest)
                except StatusError:
                    unreadable += 1
        for versions in groups.values():
            versions.sort(key=lambda version: (moment(version["received_at"]), version["id"]), reverse=True)
        return groups, unreadable

    def versions(self, series):
        """The versions of one series, newest first; empty when nothing was published in it."""
        return self._series()[0].get(series, [])

    def _resolve(self, identifier):
        """(version, versions of its series) for a version identifier, or for a series identifier its latest version."""
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise StatusError("Invalid delivery identifier.")
        groups = self._series()[0]
        for versions in groups.values():
            for version in versions:
                if version["id"] == identifier:
                    return version, versions
        if identifier in groups:
            return groups[identifier][0], groups[identifier]
        self.manifest(identifier)                   # an unreadable record reports its own reason
        raise StatusError("This delivery is unavailable.")

    def state(self, series):
        """The user's response state for a series, in the current shape whenever it was written."""
        if not isinstance(series, str) or not IDENTIFIER.fullmatch(series):
            raise StatusError("Invalid delivery identifier.")
        path = self.root / "delivery-state" / (series + ".json")
        state = {"read_at": None, "read_version": None, "response": None, "discussed_at": None, "history": []}
        if path.exists() or path.is_symlink():
            try:
                saved = json.loads(read_text(path, 1024 * 1024))
                if not isinstance(saved, dict) or set(saved) not in (STATE_FIELDS, EARLIER_STATE_FIELDS) or not isinstance(saved["history"], list):
                    raise ValueError("Invalid delivery state")
                # A record from before versions was given on the only version there was, whose identifier is the series.
                saved.setdefault("read_version", series if saved["read_at"] else None)
                if saved["response"] is not None:
                    saved["response"].setdefault("version", series)
                state = saved
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                raise StatusError("The delivery's saved responses cannot be read.") from error
        return state

    def _record(self, manifest, versions):
        series = series_identity(manifest)
        state, latest = self.state(series), versions[0]
        numbers = {version["id"]: len(versions) - index for index, version in enumerate(versions)}
        response, unread = state["response"], state["read_version"] != latest["id"]
        return {**manifest, **state, "status": response["type"] if response else "new" if unread else "read",
                "unread": unread, "series": series, "key": manifest.get("key"), "version": latest["id"],
                "version_count": len(versions), "number": numbers[manifest["id"]], "latest": manifest["id"] == latest["id"],
                "response_version_number": numbers.get(response["version"]) if response else None,
                "first_received_at": versions[-1]["received_at"],
                "versions": [{"id": version["id"], "received_at": version["received_at"]} for version in versions],
                "document_state": self.states.summary(series) if any(version["interactive"] for version in versions) else None}

    def record(self, identifier):
        """One version (the latest, for a series identifier) with the user's response state for its series."""
        return self._record(*self._resolve(identifier))

    def list(self):
        """One record per series: its latest version, newest first."""
        groups, unreadable = self._series()
        deliveries = []
        for versions in groups.values():
            try:
                deliveries.append(self._record(versions[0], versions))
            except StatusError:
                unreadable += 1
        deliveries.sort(key=lambda delivery: (moment(delivery["received_at"]), delivery["id"]), reverse=True)
        return {"deliveries": deliveries, "unreadable": unreadable}

    def document(self, identifier):
        manifest = self.manifest(identifier)
        return read_text(self._directory(identifier) / "document.md", DOCUMENT_LIMIT) if manifest["has_document"] else None

    def interactive_document(self, identifier):
        """The retained HTML of a version's interactive document. It is served only inside a sandbox."""
        if (self.manifest(identifier)["interactive"] or {}).get("kind") != "document":
            raise StatusError("This delivery has no retained interactive document.")
        return read_text(self._directory(identifier) / interactive_documents.DOCUMENT_NAME, interactive_documents.DOCUMENT_LIMIT)

    def attachment(self, identifier, index):
        manifest = self.manifest(identifier)
        if type(index) is not int or not 0 <= index < len(manifest["attachments"]):
            raise StatusError("This attachment is unavailable.")
        return manifest["attachments"][index], read_text(self._directory(identifier) / "attachments" / str(index), ATTACHMENT_LIMIT)

    def respond(self, identifier, action, *, choice=None, note=None):
        """Record one user response on the latest version, with its time, and return the updated record.

        `identifier` names the version the user was looking at. A response to
        anything but the latest version is refused, so a choice is never
        recorded against content he has not seen; opening an earlier version
        records nothing.
        """
        manifest = self.manifest(identifier)
        if action not in ACTIONS:
            raise StatusError("Choose read, accept, dismiss, discuss, or reopen.")
        if note is not None and (not isinstance(note, str) or len(note) > 4000):
            raise StatusError("A note is text of at most 4000 characters.")
        note = note.strip() or None if note else None
        if action == "accept":
            options = (manifest.get("decision") or {}).get("options", [])
            if choice == RECOMMENDED and not manifest.get("recommended_default"):
                raise StatusError("This delivery has no recommended default to accept.")
            if choice != RECOMMENDED and choice not in options:
                raise StatusError("Choose the recommended default or one of the delivery's options.")
        elif choice is not None:
            raise StatusError("A choice applies only when accepting.")
        if action == "discuss" and not manifest.get("thread"):
            raise StatusError("This delivery has no linked Ribbon Field thread.")
        series = series_identity(manifest)
        directory = self.root / "delivery-state"
        directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(directory / (series + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            versions = self.versions(series)
            if versions[0]["id"] != identifier:
                if action == "read":
                    return self._record(manifest, versions)       # an earlier version never clears a newer one
                raise ResponseConflict("A newer version of this delivery has arrived. Open the latest version before responding.")
            state, now = self.state(series), datetime.now(timezone.utc).isoformat()
            event = {"action": action, "at": now, "version": identifier}
            if action == "read":
                if state["read_version"] == identifier:
                    return self._record(manifest, versions)       # only the first opening of a version is a response
            elif action == "accept":
                state["response"] = {"type": "accepted", "choice": choice, "note": note, "at": now, "version": identifier}
                event.update(choice=choice, note=note)
            elif action == "dismiss":
                state["response"] = {"type": "dismissed", "choice": None, "note": note, "at": now, "version": identifier}
                event.update(note=note)
            elif action == "discuss":
                state["discussed_at"] = now
            elif state["response"] is None:
                return self._record(manifest, versions)
            else:
                state["response"] = None
            state["read_at"] = state["read_at"] or now
            if action != "reopen":                  # withdrawing a response says nothing about having read a newer version
                state["read_version"] = identifier
            state["history"] = (state["history"] + [event])[-200:]
            write_json(directory / (series + ".json"), state)
        return self._record(manifest, self.versions(series))
