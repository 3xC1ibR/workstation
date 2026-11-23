#!/usr/bin/env python3
"""Capture screenshots of a built report at desktop and phone width, in light and dark themes.

Uses headless Google Chrome or Chromium; no Python packages are needed. The phone
view is captured through a 390 px frame because headless Chrome will not make a
window narrower than about 500 px. Long pages are captured in parts of at most
2700 px so each image stays readable when an agent or critic opens it.
"""
from __future__ import annotations

import argparse
import html
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
]
PART = 2700


def browser():
    for candidate in [os.environ.get("CHROME")] + CANDIDATES:
        if candidate and (Path(candidate).exists() or shutil.which(candidate)):
            return candidate
    raise SystemExit("No Chrome or Chromium found; set CHROME to its executable.")


def capture(chrome, url, output, width, height, theme):
    scheme = "1" if theme == "light" else "0"         # Blink: 0 dark, 1 light
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--blink-settings=preferredColorScheme={scheme}",
                    f"--window-size={width},{height}", f"--screenshot={output}", url],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Built report HTML (from build_status.py --output)")
    parser.add_argument("--out", type=Path, required=True, help="Directory for the PNG files")
    parser.add_argument("--height", type=int, default=5400, help="Page height to capture, in CSS pixels")
    parser.add_argument("--themes", default="light,dark")
    args = parser.parse_args()
    chrome, report = browser(), args.report.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    written = []
    with tempfile.TemporaryDirectory() as scratch:
        for theme in args.themes.split(","):
            for index, top in enumerate(range(0, args.height, PART)):
                desktop = args.out / f"desktop-{theme}-{index + 1}.png"
                frame = Path(scratch) / f"desktop-{theme}-{index}.html"
                frame.write_text(_frame(report, 1280, top), encoding="utf-8")
                capture(chrome, frame.as_uri(), desktop, 1280, PART, theme)
                phone = args.out / f"phone-{theme}-{index + 1}.png"
                frame = Path(scratch) / f"phone-{theme}-{index}.html"
                frame.write_text(_frame(report, 390, top), encoding="utf-8")
                capture(chrome, frame.as_uri(), phone, 600, PART, theme)
                written += [desktop, phone]
    for path in written:
        print(path)


def _frame(report, width, top):
    source = html.escape(report.as_uri(), quote=True)
    return (f'<!doctype html><html><body style="margin:0;overflow:hidden"><div style="width:{width}px;height:{PART}px;overflow:hidden">'
            f'<iframe src="{source}" style="width:{width}px;height:{top + PART}px;border:0;display:block;margin-top:-{top}px">'
            f"</iframe></div></body></html>")


if __name__ == "__main__":
    sys.exit(main())
