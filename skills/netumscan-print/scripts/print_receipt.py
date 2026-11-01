#!/usr/bin/env python3
"""Prepare or submit one bounded text or monochrome image print over USB."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import textwrap

VENDOR_ID = 0x0416
PRODUCT_ID = 0x5011
SERIAL_NUMBER = "83600000000"
STATE_DIRECTORY = Path.home() / ".local/state/netumscan-printer"
COLUMNS = 48
MAX_LINES = 120
MAX_IMAGE_WIDTH = 576
MAX_IMAGE_HEIGHT = 4096
MAX_EXTENDED_IMAGE_HEIGHT = 16384


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def prepare_text(text):
    replacements = str.maketrans({
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--", "\u2026": "...", "\u00a0": " ",
        "\u2022": "*",
    })
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    text = text.translate(replacements)
    if any(ord(character) < 32 and character != "\n" or ord(character) == 127
           for character in text):
        raise ValueError("Receipt text contains a control character; ESC/POS commands are not accepted as text.")
    text.encode("cp437", errors="strict")
    lines = []
    for paragraph in text.splitlines():
        lines.extend(textwrap.wrap(paragraph, width=COLUMNS, replace_whitespace=False,
                                   drop_whitespace=True) or [""])
    if not lines or not any(line.strip() for line in lines):
        raise ValueError("Receipt text is empty.")
    if len(lines) > MAX_LINES:
        raise ValueError(f"Receipt exceeds {MAX_LINES} lines; prepare a shorter receipt.")
    return "\n".join(lines) + "\n"


def prepare_payload(text, calibration):
    # Initialize, disable multibyte mode, select code page 0 / font A / normal size.
    prefix = b"\x1b@\x1c.\x1bt\x00\x1bM\x00\x1d!\x00\x1ba\x00\x1b2"
    if calibration:
        text = (
            "NETUMSCAN USB TEST\n"
            "Model: NS8360L   Paper: 80 mm\n"
            f"Date: {datetime.now().astimezone():%Y-%m-%d %H:%M %Z}\n"
            + "-" * COLUMNS + "\n"
            "Normal text: 12 x 24 dot font\n"
            "The quick brown fox jumps over the lazy dog.\n"
            "012345678901234567890123456789012345678901234567\n"
            "|<-------------- 48 columns ------------------>|\n"
            "Check: readable text and intact right edge.\n"
            "Check: the cutter leaves a small joining tab.\n"
            + "-" * COLUMNS + "\n"
            "End of test\n"
        )
        text = prepare_text(text)
        title, body = text.split("\n", 1)
        data = (prefix + b"\x1ba\x01\x1bE\x01\x1d!\x11"
                + title.encode("cp437") + b"\n"
                + b"\x1d!\x00\x1bE\x00\x1ba\x00"
                + body.encode("cp437"))
    else:
        text = prepare_text(text)
        data = prefix + text.encode("cp437")
    # Feed two lines, then feed to the cutter and make one partial cut (GS V B 0).
    return text, data + b"\n\n\x1dVB\x00"


def prepare_image(path, maximum_height=MAX_IMAGE_HEIGHT):
    from PIL import Image, ImageOps
    if not 1 <= maximum_height <= MAX_EXTENDED_IMAGE_HEIGHT:
        raise ValueError("Image height limit must be between 1 and 16384 dots.")
    with Image.open(path) as original:
        if original.format != "PNG" or getattr(original, "n_frames", 1) != 1:
            raise ValueError("Image input must be a single-frame PNG.")
        if not 1 <= original.width <= MAX_IMAGE_WIDTH or not 1 <= original.height <= maximum_height:
            raise ValueError(f"PNG must be at most {MAX_IMAGE_WIDTH} x {maximum_height} pixels; reflow at 8 dots/mm.")
        rgba = original.convert("RGBA")
        paper = Image.new("RGBA", rgba.size, "white")
        paper.alpha_composite(rgba)
        monochrome = paper.convert("L").convert("1", dither=Image.Dither.NONE)
    if ImageOps.invert(monochrome.convert("L")).getbbox() is None:
        raise ValueError("PNG contains no printable marks.")
    padded_width = (monochrome.width + 7) // 8 * 8
    padded = Image.new("1", (padded_width, monochrome.height), 1)
    padded.paste(monochrome, (0, 0))
    # ESC/POS uses 1 for printed dots. White padding must remain zero after inversion.
    raster = bytes(value ^ 0xff for value in padded.tobytes())
    row_bytes = padded_width // 8
    payload = bytearray(b"\x1b@\x1ba\x00")
    for row in range(0, monochrome.height, 128):
        rows = min(128, monochrome.height - row)
        payload.extend(b"\x1dv0\x00" + row_bytes.to_bytes(2, "little") + rows.to_bytes(2, "little"))
        payload.extend(raster[row * row_bytes:(row + rows) * row_bytes])
    payload.extend(b"\n\n\x1dVB\x00")
    return monochrome, bytes(payload)


def open_printer():
    import usb.core
    import usb.util
    printer = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID,
                            serial_number=SERIAL_NUMBER)
    if printer is None:
        raise RuntimeError("NetumScan USB printer not found; check power and the USB cable.")
    try:
        interface = printer.get_active_configuration()[(0, 0)]
        endpoints = {endpoint.bEndpointAddress for endpoint in interface}
        if interface.bInterfaceClass != 7 or not {0x01, 0x81}.issubset(endpoints):
            raise RuntimeError("USB printer interface differs from the verified configuration.")
        usb.util.claim_interface(printer, 0)
    except Exception:
        usb.util.dispose_resources(printer)
        raise
    return printer


def read_status(printer):
    values = {}
    for selector, name in enumerate(("printer", "offline", "error", "paper"), 1):
        printer.write(0x01, bytes([0x10, 0x04, selector]), timeout=2000)
        response = bytes(printer.read(0x81, 1, timeout=2000))
        if len(response) != 1 or response[0] & 0x93 != 0x12:
            raise RuntimeError(f"Unexpected response for {name} status: {response.hex()}")
        values[name] = response[0]
    faults = []
    if values["printer"] & 0x08:
        faults.append("offline")
    if values["offline"] & 0x04:
        faults.append("cover open")
    if values["offline"] & 0x20 or values["paper"] & 0x60:
        faults.append("paper empty")
    if values["offline"] & 0x40 or values["error"] & 0x68:
        faults.append("printer or cutter error")
    return {"raw": {name: f"{value:02x}" for name, value in values.items()},
            "ready": not faults, "faults": faults,
            "paper_near_end": bool(values["paper"] & 0x0c)}


def save_record(path, record):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--status", action="store_true", help="Read hardware status without feeding paper.")
    source.add_argument("--test", action="store_true", help="Prepare the short calibration receipt.")
    source.add_argument("--text", help="Receipt text; typography is normalized to CP437.")
    source.add_argument("--file", type=Path, help="UTF-8 text file to wrap at 48 columns.")
    source.add_argument("--image", type=Path, help="Single-frame PNG, up to 576 x 4096 pixels; one pixel per dot.")
    parser.add_argument("--maximum-length-mm", type=int, help="Explicit image length bound, 1-2048 mm; default 512 mm.")
    parser.add_argument("--submit", action="store_true", help="Print one copy and make one partial cut.")
    parser.add_argument("--output-directory", type=Path, help="New runtime directory; must not already exist.")
    arguments = parser.parse_args()
    if arguments.maximum_length_mm is not None:
        if not arguments.image or not 1 <= arguments.maximum_length_mm <= 2048:
            parser.error("--maximum-length-mm requires --image and a value from 1 to 2048")
    if arguments.status:
        if arguments.submit or arguments.output_directory:
            parser.error("--status cannot be combined with --submit or --output-directory")
        import usb.util
        printer = open_printer()
        try:
            print(json.dumps(read_status(printer), indent=2))
        finally:
            usb.util.dispose_resources(printer)
        return

    image_preview = None
    if arguments.image:
        maximum_height = arguments.maximum_length_mm * 8 if arguments.maximum_length_mm is not None else MAX_IMAGE_HEIGHT
        image_preview, payload = prepare_image(arguments.image, maximum_height)
        preview = f"Monochrome image: {image_preview.width} x {image_preview.height} dots\n"
    else:
        text = arguments.file.read_text(encoding="utf-8") if arguments.file else arguments.text
        preview, payload = prepare_payload(text, arguments.test)
    directory = arguments.output_directory or (
        STATE_DIRECTORY / "jobs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"))
    directory = directory.expanduser().resolve()
    if directory.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("Keep generated output outside the skill source directory.")
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "preview.txt").write_text(preview, encoding="utf-8")
    if image_preview is not None:
        image_preview.save(directory / "preview.png")
    (directory / "payload.escpos").write_bytes(payload)
    record = {"created_at": timestamp(), "state": "prepared", "copies": 1,
              "vendor_id": "0416", "product_id": "5011", "serial": SERIAL_NUMBER,
              "payload_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
              "cut": "partial", "physical_output": "unconfirmed", "directory": str(directory)}
    if image_preview is not None:
        record.update(mode="raster", image_width=image_preview.width,
                      image_height=image_preview.height, feed_length_mm=image_preview.height / 8,
                      image_source=str(arguments.image.resolve()),
                      image_sha256=hashlib.sha256(arguments.image.read_bytes()).hexdigest())
    else:
        record.update(mode="text", columns=COLUMNS, lines=len(preview.splitlines()))
    receipt = directory / "receipt.json"
    save_record(receipt, record)
    if not arguments.submit:
        print(preview, end="")
        print(json.dumps(record, indent=2))
        return

    import usb.util
    printer = None
    transfer_started = False
    try:
        printer = open_printer()
        record["status_before"] = read_status(printer)
        if not record["status_before"]["ready"]:
            raise RuntimeError("Printer is not ready: " + ", ".join(record["status_before"]["faults"]))
        record.update(state="submission_started", submitted_at=timestamp())
        save_record(receipt, record)
        transfer_started = True
        transferred = printer.write(0x01, payload, timeout=30000 if image_preview is not None else 10000)
        record["bytes_transferred"] = transferred
        if transferred != len(payload):
            raise RuntimeError(f"Partial USB transfer: {transferred}/{len(payload)} bytes; inspect output before retrying.")
        record.update(state="usb_transfer_complete", transferred_at=timestamp())
        save_record(receipt, record)
        try:
            record["status_after"] = read_status(printer)
        except Exception as error:
            record["status_after_error"] = str(error)
    except Exception as error:
        record.update(state="transfer_uncertain" if transfer_started else "not_submitted", error=str(error))
        save_record(receipt, record)
        raise
    finally:
        if printer is not None:
            usb.util.dispose_resources(printer)
    save_record(receipt, record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
