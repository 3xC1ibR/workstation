#!/usr/bin/env python3
"""Check a PDF against the selected paper size, then optionally print once."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--media", choices=("Letter", "A4"), required=True)
    parser.add_argument("--queue", default="M832D-Q769")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--receipt", type=Path)
    arguments = parser.parse_args()
    document = arguments.pdf.expanduser().resolve(strict=True)
    expected = {"Letter": (612, 792), "A4": (595.2756, 841.8898)}[arguments.media]
    reader = PdfReader(document)
    if reader.is_encrypted:
        parser.error("Use an unencrypted PDF for printing")
    if not reader.pages:
        parser.error("The PDF has no pages")
    for number, page in enumerate(reader.pages, 1):
        if page.get("/UserUnit", 1) != 1:
            parser.error(f"Page {number} uses a nonstandard PDF measurement scale; normalize it first")
        dimensions = (float(page.mediabox.width), float(page.mediabox.height))
        if page.rotation % 180:
            dimensions = tuple(reversed(dimensions))
        if any(abs(actual - wanted) > 1 for actual, wanted in zip(dimensions, expected)):
            parser.error(f"Page {number} is {dimensions} points; reformat it to portrait {arguments.media} first")
        if list(page.cropbox) != list(page.mediabox):
            parser.error(f"Page {number} has a cropped view; normalize and review it before printing")

    subprocess.run(["lpstat", "-p", arguments.queue], check=True, capture_output=True, text=True)
    command = [
        "lp", "-d", arguments.queue, "-n", "1",
        "-t", document.stem,
        "-o", f"media={arguments.media}",
        "-o", "sides=one-sided", "-o", "print-scaling=none",
        "-o", "fit-to-page=false", "-o", "Resolution=300dpi",
        "-o", "ColorOption=GrayScale", "-o", "zeMediaTracking=Continuous",
        str(document),
    ]
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pdf": str(document), "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
        "page_count": len(reader.pages), "media": arguments.media,
        "queue": arguments.queue, "copies": 1, "command": command,
        "status": "preflight_passed", "physical_output_confirmed": False,
    }
    if not arguments.submit:
        print(json.dumps(record, indent=2))
        return
    if arguments.receipt is None:
        parser.error("Submission requires --receipt pointing outside the skill repository")
    receipt = arguments.receipt.expanduser().resolve()
    source_root = Path(__file__).resolve().parents[1]
    repository_root = next((parent for parent in source_root.parents if (parent / ".git").exists()), source_root)
    if receipt.is_relative_to(repository_root):
        parser.error("Keep print receipts outside the skill repository")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error(f"Receipt already exists: {receipt}. Inspect it and CUPS before any retry")
    record["status"] = "submission_started"
    with os.fdopen(descriptor, "w") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")

    def save() -> None:
        temporary = receipt.with_suffix(receipt.suffix + ".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(receipt)

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        record["status"] = "submission_uncertain"
        save()
        raise
    record.update({"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()})
    job = re.search(r"request id is (\S+)", result.stdout)
    if result.returncode == 0 and job:
        record.update({"status": "accepted_by_cups", "job_id": job.group(1)})
    else:
        record["status"] = "submission_unconfirmed"
    save()
    print(json.dumps(record, indent=2))
    if record["status"] != "accepted_by_cups":
        raise SystemExit("Inspect this receipt and CUPS history before submitting again")


if __name__ == "__main__":
    main()
