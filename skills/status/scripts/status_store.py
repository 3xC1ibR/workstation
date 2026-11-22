"""Global generated status reports and durable, reversible user dismissal.

Producers atomically publish immutable directories containing manifest.json,
report.json and report.html. The inbox is independent of workspaces, providers,
and any application. Only user review changes dismissal records.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from status_fields import validate_fields, validate_values

class StatusError(ValueError):
    """An unreadable or unsupported status inbox record."""


class ResponseConflict(StatusError):
    """A response changed after the editor loaded its previous revision."""

IDENTIFIER = re.compile(r"[a-f0-9]{64}\Z")
REPORT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
              "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox allow-popups allow-popups-to-escape-sandbox")


class StatusReports:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(os.environ.get(
            "AGENT_STATUS_INBOX", Path.home() / ".local/state/agent-status/inbox")).expanduser()

    def _directory(self, identifier):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise StatusError("Invalid status report identifier.")
        directory = self.root / "reports" / identifier
        if directory.is_symlink() or not directory.is_dir():
            raise StatusError("This status report is unavailable.")
        return directory

    def _read(self, path, maximum):
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
                    raise StatusError("The status record is not a supported file.")
                content = source.read(maximum + 1)
                if len(content) > maximum:
                    raise StatusError("The status record is too large.")
                return content.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise StatusError("The status report cannot be read.") from error

    def _manifest(self, identifier):
        directory = self._directory(identifier)
        try:
            manifest = json.loads(self._read(directory / "manifest.json", 256 * 1024))
            if manifest.get("version") != 1 or manifest.get("id") != identifier:
                raise ValueError("Unsupported report record")
            for field in ("title", "subject", "summary", "generated_at", "received_at"):
                if not isinstance(manifest[field], str) or not manifest[field].strip():
                    raise ValueError("Missing report field")
            for field in ("generated_at", "received_at"):
                if datetime.fromisoformat(manifest[field].replace("Z", "+00:00")).utcoffset() is None:
                    raise ValueError("Timezone required")
            origin = manifest["origin"]
            if not isinstance(origin, dict) or any(value is not None and not isinstance(value, str) for value in origin.values()):
                raise ValueError("Invalid report origin")
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise StatusError("The status report record is invalid.") from error
        state = self.root / "dismissed" / (identifier + ".json")
        dismissed_at = None
        if state.exists() or state.is_symlink():
            try:
                dismissed_at = json.loads(self._read(state, 4096))["dismissed_at"]
                if not isinstance(dismissed_at, str):
                    raise ValueError("Invalid dismissal")
            except (ValueError, KeyError, TypeError) as error:
                raise StatusError("The report's dismissal record is invalid.") from error
        return {**manifest, "dismissed_at": dismissed_at}

    def list(self):
        reports, unreadable = [], 0
        directory = self.root / "reports"
        if directory.exists():
            for entry in directory.iterdir():
                if not IDENTIFIER.fullmatch(entry.name):
                    continue
                try:
                    reports.append(self._manifest(entry.name))
                except StatusError:
                    unreadable += 1
        reports.sort(key=lambda report: (datetime.fromisoformat(report["received_at"].replace("Z", "+00:00")), report["id"]), reverse=True)
        return {"reports": reports, "unreadable": unreadable}

    def content(self, identifier):
        self._manifest(identifier)
        return self._read(self._directory(identifier) / "report.html", 8 * 1024 * 1024)

    def response_fields(self, identifier):
        self._manifest(identifier)
        try:
            document = json.loads(self._read(self._directory(identifier) / "report.json", 8 * 1024 * 1024))
            fields = document.get("response_fields", [])
            validate_fields(fields)
            return fields
        except (ValueError, AttributeError) as error:
            raise StatusError("The report's response fields cannot be read.") from error

    def responses(self, identifier):
        manifest = self._manifest(identifier)
        fields = self.response_fields(identifier)
        path = self.root / "responses" / (identifier + ".json")
        state = {"revision": 0, "updated_at": None, "values": {}}
        if path.exists() or path.is_symlink():
            try:
                state = json.loads(self._read(path, 2 * 1024 * 1024))
                if (not isinstance(state, dict) or set(state) != {"revision", "updated_at", "values"}
                        or type(state["revision"]) is not int or state["revision"] < 1
                        or datetime.fromisoformat(state["updated_at"].replace("Z", "+00:00")).utcoffset() is None):
                    raise ValueError("Invalid response record")
                state["values"] = validate_values(fields, state["values"])
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                raise StatusError("The report's saved responses cannot be read.") from error
        return {"id": identifier, "title": manifest["title"], "origin": manifest["origin"],
                "fields": fields, **state}

    def save_responses(self, identifier, values, revision):
        fields = self.response_fields(identifier)
        if not fields:
            raise StatusError("This report has no response fields.")
        if type(revision) is not int or revision < 0:
            raise StatusError("A nonnegative response revision is required.")
        values = validate_values(fields, values)
        directory = self.root / "responses"
        directory.mkdir(parents=True, exist_ok=True)
        # Separate processes and server threads share the same per-report lock.
        descriptor = os.open(directory / (identifier + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.responses(identifier)["revision"] != revision:
                raise ResponseConflict("Responses changed in another page. Load saved responses before saving again; your input is still here.")
            state = {"revision": revision + 1, "updated_at": datetime.now(timezone.utc).isoformat(), "values": values}
            descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                    json.dump(state, target, ensure_ascii=False, allow_nan=False)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, directory / (identifier + ".json"))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return {"id": identifier, "fields": fields, **state}

    def dismiss(self, identifier, dismissed):
        if type(dismissed) is not bool:
            raise StatusError("Choose dismissed: true or false.")
        self._manifest(identifier)
        directory = self.root / "dismissed"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (identifier + ".json")
        if dismissed:
            descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
            try:
                with os.fdopen(descriptor, "w") as target:
                    json.dump({"dismissed_at": datetime.now(timezone.utc).isoformat()}, target)
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        else:
            destination.unlink(missing_ok=True)
        return self._manifest(identifier)
