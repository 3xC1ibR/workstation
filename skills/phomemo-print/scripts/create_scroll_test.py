#!/usr/bin/env python3
"""Create one short sideways scroll test with three sequential reading columns."""

import argparse
from pathlib import Path

import reportlab
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


def create_test(output: Path) -> None:
    physical_width = 215.9 * mm
    physical_length = 320 * mm
    font_directory = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("ScrollSans", str(font_directory / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("ScrollBold", str(font_directory / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("ScrollSans", normal="ScrollSans", bold="ScrollBold")
    output.parent.mkdir(parents=True, exist_ok=True)
    page = canvas.Canvas(str(output), pagesize=(physical_width, physical_length), initialFontName="ScrollSans")
    page.setTitle("Sideways scroll orientation test")
    page.setAuthor("Workstation")

    # Keep the physical PDF portrait for the printer. Rotate its content so the
    # leading paper edge becomes the left end of the horizontal reading surface.
    page.translate(0, physical_length)
    page.rotate(-90)
    width, height = physical_length, physical_width
    left, right = 12 * mm, width - 12 * mm
    bottom, top = 10 * mm, height - 10 * mm
    page.setLineWidth(.5)
    page.rect(left, bottom, right - left, top - bottom)
    inset = 4 * mm
    page.setFont("ScrollBold", 18)
    page.drawString(left + inset, top - 9 * mm, "SIDEWAYS SCROLL TEST")
    page.setFont("ScrollSans", 10)
    page.drawString(left + inset, top - 16 * mm, "Hold the roll lengthwise. Read column 1, then 2, then 3. Unroll to the right.")
    page.drawString(left + inset, top - 23 * mm, "One strip: 320 mm long x 215.9 mm high | 10 pt text | 13.5 pt line spacing")
    rule_y = top - 28 * mm
    page.line(left + inset, rule_y, right - inset, rule_y)

    columns = [
        ("1. START HERE", [
            "This is the beginning of the scroll. The words should be upright when you hold the long strip from left to right, with a rolled end at either side.",
            "Each line runs along the length of the paper. Each column is read from top to bottom. After finishing one column, move to the next column on its right.",
            "The paper can curl naturally at the ends. You only need to expose the section you are reading, rather than flattening a whole sheet or tearing off individual pages.",
            "This test uses the same 10-point type size you found comfortable on the first calibration page.",
        ]),
        ("2. KEEP UNROLLING", [
            "This is the second reading column. A complete article would continue into this space, keeping its original wording and reading order.",
            "The columns give your eyes a manageable line length. As you read, you can roll up the finished portion on the left and release more paper on the right.",
            "Headings, paragraphs, and illustrations can follow the same direction. The layout should feel like reading across an open scroll, rather than turning a stack of pages.",
            "There is no page boundary between these columns. All three are printed together on one continuous custom-length strip.",
        ]),
        ("3. FINISH HERE", [
            "This is the end of the test strip. The numbered columns should have appeared in order as you unrolled it.",
            "Check whether the text faces the way you expected, whether the short lines feel comfortable, and whether the rolled ends stay out of the section you are reading.",
            "This layout is intended for the paper roll currently installed. The straight, folded paper you ordered can use regular portrait pages after it arrives and is loaded.",
            "For this test, keep the strip whole. We can use your physical result to settle the direction and column width before formatting an entire article.",
        ]),
    ]
    gap = 8 * mm
    column_width = (right - left - 2 * inset - 2 * gap) / 3
    body = ParagraphStyle("ScrollBody", fontName="ScrollSans", fontSize=10, leading=13.5, spaceAfter=8)
    for index, (heading, paragraphs) in enumerate(columns):
        x = left + inset + index * (column_width + gap)
        y = rule_y - 9 * mm
        page.setFont("ScrollBold", 12)
        page.drawString(x, y, heading)
        y -= 7 * mm
        for text in paragraphs:
            paragraph = Paragraph(text, body)
            _, paragraph_height = paragraph.wrap(column_width, height)
            if y - paragraph_height < bottom + 27 * mm:
                raise ValueError("Scroll test content exceeds its reading area")
            paragraph.drawOn(page, x, y - paragraph_height)
            y -= paragraph_height + body.spaceAfter

    scale_y = bottom + 14 * mm
    scale_left = left + inset
    page.setLineWidth(.7)
    page.line(scale_left, scale_y, scale_left + 100 * mm, scale_y)
    for index in range(11):
        x = scale_left + index * 10 * mm
        page.line(x, scale_y - 2, x, scale_y + (5 if index % 5 == 0 else 3))
    page.setFont("ScrollSans", 8)
    page.drawString(scale_left, scale_y - 12, "100 mm along the unrolling direction")
    page.setFont("ScrollBold", 10)
    page.drawRightString(right - inset, scale_y, "READ LEFT TO RIGHT  ->")
    page.showPage()
    page.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    create_test(arguments.output.expanduser())
    print(arguments.output.expanduser().resolve())


if __name__ == "__main__":
    main()
