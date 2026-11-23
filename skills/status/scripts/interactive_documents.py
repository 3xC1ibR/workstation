"""Interactive documents: content an agent builds, shown inside an item's page.

An operation report version or a delivery may carry one interactive document:
either one retained HTML file or the address of another application on the
same host. Both are shown in a sandboxed frame that never receives the page's
origin, because that origin is shared with Ribbon Field. This module holds the
validation and the frame policy shared by producers, stores and the service.
"""
from __future__ import annotations

from pathlib import Path
import re

# The frame may run scripts and forms, open dialogs and sandboxed windows, and download. It never gets
# allow-same-origin, top navigation, or windows that escape the sandbox.
SANDBOX = "allow-scripts allow-forms allow-modals allow-popups allow-downloads"
# The one browser permission the frame is given: a document may write to the clipboard (its Copy control), never read it.
PERMISSIONS = "clipboard-write"
# Sent with every retained document, so it has an opaque origin even when its address is opened in a tab.
DOCUMENT_POLICY = f"sandbox {SANDBOX}; frame-ancestors 'self'"
DOCUMENT_LIMIT = 4 * 1024 * 1024
DOCUMENT_NAME = "interactive.html"
ADDRESS = re.compile(r"(?:/[A-Za-z0-9._~-]+)+/?\Z")
ADDRESS_LIMIT = 500


def validate_address(address, prefix=None):
    """Check the path of another application on the same host; `prefix` is the review page's own path there."""
    if (not isinstance(address, str) or len(address) > ADDRESS_LIMIT or not ADDRESS.fullmatch(address)
            or any(part in {".", ".."} for part in address.split("/"))):
        raise ValueError("An embedded address is a path on the tailnet host, such as /thanksgiving/: letters, digits, "
                         "'.', '_', '~' and '-' between slashes, with no '..', host, query or fragment")
    if prefix is not None and (not prefix or address == prefix or address.startswith(prefix + "/")):
        raise ValueError("An embedded address names another application on the host, not the review page itself")
    return address


def read_document(path):
    """Read the HTML file an agent wants retained, within the size limit."""
    path = Path(path)
    if path.stat().st_size > DOCUMENT_LIMIT:
        raise ValueError(f"{path.name}: an interactive document is one HTML file of at most 4 MB")
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{path.name}: an interactive document must be UTF-8 text") from error


def source(document=None, address=None, prefix=None):
    """Validate the one form given and return (manifest record, retained content); both are None without either."""
    if document is not None and address is not None:
        raise ValueError("Give one interactive document or one embedded address, not both")
    if document is not None:
        if not isinstance(document, str) or not document.strip() or len(document.encode()) > DOCUMENT_LIMIT:
            raise ValueError("An interactive document is one nonempty HTML file of at most 4 MB")
        return {"kind": "document", "address": None}, document
    if address is not None:
        return {"kind": "address", "address": validate_address(address, prefix)}, None
    return None, None


def recorded(manifest):
    """The validated interactive record of a stored manifest, or None when the item has none."""
    record = manifest.get("interactive")
    if record is None:
        return None
    if not isinstance(record, dict) or set(record) != {"kind", "address"}:
        raise ValueError("Invalid interactive record")
    if record["kind"] == "document" and record["address"] is None:
        return record
    if record["kind"] == "address":
        validate_address(record["address"])
        return record
    raise ValueError("Invalid interactive record")
