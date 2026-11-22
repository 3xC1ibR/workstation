"""Access keys let a portable report read and update only its own responses."""
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile


def response_key(root, identifier, *, create=False):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{64}", identifier):
        raise ValueError("Invalid status report identifier.")
    directory = Path(root) / "response-keys"
    destination = directory / identifier
    if create and not destination.exists():
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as target:
                target.write(secrets.token_urlsafe(32))
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary)
    descriptor = os.open(destination, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="ascii") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Invalid report response access key.")
        value = source.read(128)
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise ValueError("Invalid report response access key.")
    return value


def connection(root, identifier, viewer_url):
    from urllib.parse import urlsplit

    address = urlsplit(viewer_url)
    port = address.port
    if (address.scheme != "http" or address.hostname not in {"127.0.0.1", "localhost"}
            or address.username or address.password or address.path not in {"", "/"}
            or address.query or address.fragment or port == 0):
        raise ValueError("The response viewer URL must be a local HTTP origin.")
    return {"id": identifier, "url": viewer_url.rstrip("/") + "/api/report-responses/" + identifier,
            "token": response_key(root, identifier, create=True)}
