#!/usr/bin/env python3
"""Create one calibration page without submitting a print job."""

import argparse
from datetime import datetime
from pathlib import Path

import reportlab
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def create_page(output: Path, media: str) -> None:
    font_directory = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("CalibrationSans", str(font_directory / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("CalibrationBold", str(font_directory / "VeraBd.ttf")))
    width, height = {"Letter": letter, "A4": A4}[media]
    horizontal_margin = 10 * mm
    vertical_margin = 12 * mm
    output.parent.mkdir(parents=True, exist_ok=True)
    page = canvas.Canvas(str(output), pagesize=(width, height), pageCompression=1)
    page.setTitle("Phomemo M832D printer calibration")
    page.setAuthor("Workstation")
    page.setStrokeColorRGB(0, 0, 0)
    page.setLineWidth(0.5)
    page.rect(horizontal_margin, vertical_margin, width - 2 * horizontal_margin, height - 2 * vertical_margin)

    left = horizontal_margin + 8
    right = width - horizontal_margin - 8
    position = height - vertical_margin - 32

    def line(text: str, size: float = 11, bold: bool = False, advance: float = 20) -> None:
        nonlocal position
        page.setFillColorRGB(0, 0, 0)
        page.setFont("CalibrationBold" if bold else "CalibrationSans", size)
        if pdfmetrics.stringWidth(text, "CalibrationBold" if bold else "CalibrationSans", size) > right - left:
            raise ValueError(f"Calibration text exceeds the available width: {text}")
        page.drawString(left, position, text)
        position -= advance

    line("PHOMEMO M832D", 21, True, 28)
    line("Printer calibration", 15, False, 29)
    line(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), 9, advance=19)
    line(f"{media} | {width / mm:.1f} x {height / mm:.1f} mm | 300 dpi | one side", 9)
    line("Border margins: 10 mm left/right, 12 mm top/bottom.", 9, advance=29)

    line("READING SIZES", 10, True, 24)
    for size in (10, 11, 12, 14):
        line(f"{size} pt: The quick brown fox jumps over the lazy dog.", size, advance=26)
    position -= 8
    line("0123456789   abcdefghijklmnopqrstuvwxyz", 11)
    line("ABCDEFGHIJKLMNOPQRSTUVWXYZ   ! ? & ( ) [ ]", 11, advance=35)

    line("ARTICLE SAMPLE", 10, True, 24)
    for text in (
        "A useful printed article is comfortable to read away from a screen.",
        "Clear black text, generous spacing, and simple figures help on",
        "thermal paper. This paragraph uses 10-point type with 13.5-point",
        "leading. Compare it with the smaller samples above.",
    ):
        line(text, 10, advance=13.5)
    position -= 26

    line("SCALE AND CONTRAST", 10, True, 24)
    scale_y = position
    page.setLineWidth(0.7)
    page.line(left, scale_y, left + 100 * mm, scale_y)
    for index in range(11):
        location = left + index * 10 * mm
        page.line(location, scale_y - 3, location, scale_y + (7 if index % 5 == 0 else 4))
    position -= 22
    line("The line above measures 100 mm at actual size.", 9, advance=26)

    for index, gray in enumerate((0.75, 0.5, 0.25, 0.0)):
        location = left + index * 58
        page.setFillGray(gray)
        page.rect(location, position - 8 * mm, 10 * mm, 8 * mm, stroke=0, fill=1)
        page.setFillGray(0)
        page.setFont("CalibrationSans", 8)
        page.drawString(location, position - 8 * mm - 13, f"{int((1 - gray) * 100)}% black")
    position -= 75

    line("CHECK THE PHYSICAL PAGE", 10, True, 22)
    for text in (
        "All four border edges should be visible, with no missing text.",
        "Check for blank bands, faint letters, skew, and extra paper feed.",
        "Tell the assistant which text size is most comfortable to read.",
    ):
        line(text, 10, advance=16)
    if position < vertical_margin + 15:
        raise ValueError("Calibration content exceeds the page height")
    page.showPage()
    page.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--media", choices=("Letter", "A4"), required=True)
    arguments = parser.parse_args()
    create_page(arguments.output.expanduser(), arguments.media)
    print(arguments.output.expanduser().resolve())


if __name__ == "__main__":
    main()
