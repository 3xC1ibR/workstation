"""What an interactive document saved for its item, readable by agents without the service.

One record per item: a delivery (every version of it) or an operation (every
report version of it). The record is whatever JSON value the document last
saved through the page, with the save time, a revision, and the version that
saved it. It is the document's own data, not a response from the user.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path

from status_store import IDENTIFIER, StatusError, moment, read_text, write_json

STATE_LIMIT = 64 * 1024
EMPTY = {"state": None, "saved_at": None, "revision": 0, "version": None}


class DocumentStates:
    def __init__(self, root):
        self.root = Path(root) / "document-state"

    def _path(self, identifier):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise StatusError("Invalid item identifier.")
        return self.root / (identifier + ".json")

    def read(self, identifier):
        """The saved record for an item, or the empty record when its document has saved nothing."""
        path = self._path(identifier)
        if not (path.exists() or path.is_symlink()):
            return dict(EMPTY)
        try:
            saved = json.loads(read_text(path, 4 * STATE_LIMIT))
            if (not isinstance(saved, dict) or set(saved) != set(EMPTY) or type(saved["revision"]) is not int
                    or saved["revision"] < 1 or not IDENTIFIER.fullmatch(saved["version"])):
                raise ValueError("Invalid document state")
            moment(saved["saved_at"])
            return saved
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise StatusError("The document's saved state cannot be read.") from error

    def save(self, identifier, state, version):
        """Replace the item's state with the value its document saved from `version`."""
        path = self._path(identifier)
        if not isinstance(version, str) or not IDENTIFIER.fullmatch(version):
            raise StatusError("Invalid item version.")
        try:
            size = len(json.dumps(state, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))    # as the page measures it
        except (ValueError, TypeError, RecursionError) as error:
            raise StatusError("Document state must be a JSON value.") from error
        if size > STATE_LIMIT:
            raise StatusError("Document state is limited to 64 KB of JSON.")
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.root / (identifier + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                revision = self.read(identifier)["revision"]
            except StatusError:
                revision = 0                        # an unreadable record is replaced by the next save
            record = {"state": state, "saved_at": datetime.now(timezone.utc).isoformat(), "revision": revision + 1, "version": version}
            write_json(path, record)
        return record

    def summary(self, identifier):
        """The record for an agent to read; an unreadable record is reported as such, never as nothing saved."""
        try:
            return self.read(identifier)
        except StatusError:
            return {**EMPTY, "unreadable": True}
