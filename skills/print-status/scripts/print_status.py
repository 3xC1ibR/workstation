#!/usr/bin/env python3
"""Print one short, upright NetumScan status update; --preview prepares only."""

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import subprocess
import sys


# Imported printer code must not leave bytecode in the version-controlled skill.
sys.dont_write_bytecode = True

MAXIMUM_LINES = 28
PRINTER_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "netumscan-print/scripts/print_receipt.py"
)
PRINTER_COMMAND = Path.home() / ".local/bin/netumscan-print"
JOB_DIRECTORY = Path.home() / ".local/state/netumscan-printer/jobs"


def prepare_receipt(text, subject=None, generated_at=None):
    """Reuse the printer's text rules and bound the complete status strip."""
    specification = importlib.util.spec_from_file_location(
        "netumscan_receipt", PRINTER_SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("NetumScan formatter is unavailable.")
    formatter = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(formatter)

    body = formatter.prepare_text(text.strip())
    title = "STATUS"
    if subject is not None:
        if not subject.strip() or "\n" in subject or "\r" in subject:
            raise ValueError("Subject must be one nonempty line.")
        title = formatter.prepare_text("STATUS: " + subject.strip()).rstrip("\n")
        if "\n" in title:
            raise ValueError("Subject and STATUS heading must fit 48 columns.")
    generated_at = generated_at or datetime.now().astimezone()
    receipt = formatter.prepare_text(
        f"{title}\nGenerated: {generated_at:%Y-%m-%d %H:%M %Z}\n"
        + "-" * formatter.COLUMNS
        + "\n"
        + body
    )
    if len(receipt.splitlines()) > MAXIMUM_LINES:
        raise ValueError(
            f"Status exceeds {MAXIMUM_LINES} printed lines including its heading; "
            "shorten the update before printing. Nothing was submitted."
        )
    return receipt


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Short status text; otherwise read UTF-8 stdin.")
    parser.add_argument("--subject", help="Optional subject for the printed heading.")
    parser.add_argument(
        "--preview", action="store_true",
        help="Prepare text and a job record without contacting the printer."
    )
    options = parser.parse_args(arguments)
    if options.text is None:
        if sys.stdin.isatty():
            parser.error("Supply --text or status text on stdin.")
        text = sys.stdin.read()
    else:
        text = options.text
    try:
        receipt = prepare_receipt(text, options.subject)
    except (ValueError, OSError) as error:
        parser.error(str(error))

    directory = JOB_DIRECTORY / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    command = [
        str(PRINTER_COMMAND), "--text", receipt,
        "--output-directory", str(directory)
    ]
    if not options.preview:
        command.append("--submit")
    # One helper invocation retains its hardware checks, record, and no-retry rule.
    result = subprocess.run(command, check=False)
    if result.returncode and (directory / "receipt.json").exists():
        print(f"Job record: {directory / 'receipt.json'}", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
