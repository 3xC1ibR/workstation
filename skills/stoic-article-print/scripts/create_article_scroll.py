#!/usr/bin/env python3
"""Lay out complete cleaned article HTML as sideways reading columns on a roll."""

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString
from PIL import Image as RasterImage
from pypdf import PdfReader, PdfWriter
import reportlab
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle


ROLL_WIDTH = 215.9 * mm
COLUMN_WIDTH = (320 - 2 * 12 - 2 * 4 - 2 * 8) / 3 * mm
GAP = 8 * mm
END_MARGIN = 16 * mm
TOP = ROLL_WIDTH - 14 * mm
BOTTOM = 14 * mm + 12
AVAILABLE_HEIGHT = TOP - BOTTOM


def inline(node):
    if isinstance(node, NavigableString):
        return html.escape(str(node))
    if node.name in ("script", "style", "nav", "button"):
        return ""
    content = "".join(inline(child) for child in node.children)
    classes = node.get("class", [])
    if node.name == "br":
        return "<br/>"
    if node.name in ("b", "strong") or "ltx_font_bold" in classes:
        return f"<b>{content}</b>"
    if node.name in ("i", "em") or "ltx_font_italic" in classes:
        return f"<i>{content}</i>"
    if node.name in ("sup", "sub"):
        return f"<{node.name}>{content}</{node.name}>"
    if node.name in ("code", "pre") or "ltx_font_typewriter" in classes:
        return f'<font name="ArticleMono">{content}</font>'
    if "ltx_bibblock" in classes:
        return content + " "
    return content


def create_scroll(arguments):
    source = arguments.source_html.expanduser().resolve(strict=True)
    output = arguments.output_directory.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory to preserve earlier editions and receipts")
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    shutil.copyfile(source, output / "source.html")
    font_directory = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (("ArticleSans", "Vera.ttf"), ("ArticleBold", "VeraBd.ttf"), ("ArticleItalic", "VeraIt.ttf"), ("ArticleBoldItalic", "VeraBI.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(font_directory / filename)))
    pdfmetrics.registerFontFamily("ArticleSans", normal="ArticleSans", bold="ArticleBold", italic="ArticleItalic", boldItalic="ArticleBoldItalic")
    mono = Path("/System/Library/Fonts/Supplemental/Courier New.ttf")
    pdfmetrics.registerFont(TTFont("ArticleMono", str(mono if mono.exists() else font_directory / "Vera.ttf")))
    size = arguments.font_size
    if not math.isfinite(size) or size <= 0:
        raise ValueError("Font size must be a positive finite number")
    body = ParagraphStyle("Body", fontName="ArticleSans", fontSize=size, leading=size * 4 / 3, spaceAfter=3, allowWidows=0, allowOrphans=0)
    caption = ParagraphStyle("Caption", parent=body, spaceAfter=5)
    heading = ParagraphStyle("Heading", parent=body, fontName="ArticleBold", fontSize=size + 2, leading=(size + 2) * 1.2, spaceBefore=5, spaceAfter=5, keepWithNext=True)
    title = ParagraphStyle("Title", parent=heading, fontSize=14, leading=16)
    metadata = ParagraphStyle("Metadata", parent=body, fontSize=8, leading=10, spaceAfter=5)
    cell_style = ParagraphStyle("Cell", parent=body, leading=size * 1.25, spaceAfter=0)
    soup = BeautifulSoup(source.read_text(), "html.parser")
    article = soup.find("article")
    if article is None:
        raise ValueError("The source must contain a complete cleaned article element")
    items = []
    images = []
    table_records = []

    def add(flowable, span=1):
        items.append((flowable, span))

    add(Paragraph(html.escape(arguments.title), title))
    add(Paragraph(html.escape(arguments.author), metadata))
    add(Paragraph(html.escape(arguments.date) + "<br/>" + html.escape(arguments.source_url), metadata))
    license_text = " | ".join(html.escape(value) for value in (arguments.license, arguments.license_url) if value)
    adaptation = f"Scroll adaptation: reflowed at {size:g} pt; source wording retained."
    add(Paragraph((license_text + "<br/>" if license_text else "") + adaptation, metadata))

    def make_table(node):
        raw_rows = []
        spans = []
        for row_number, row in enumerate(node.find_all("tr")):
            values = []
            for cell in row.find_all(["td", "th"], recursive=False):
                if int(cell.get("rowspan", 1)) != 1:
                    raise ValueError("Normalize vertical table spans before scroll layout")
                count = int(cell.get("colspan", 1))
                start = len(values)
                value = inline(cell)
                values.append(value)
                values.extend([""] * (count - 1))
                if count > 1:
                    spans.append(("SPAN", (start, row_number), (start + count - 1, row_number)))
            raw_rows.append(values)
        columns = max(map(len, raw_rows))
        span = 2 if columns > 2 else 1
        width = span * COLUMN_WIDTH + (span - 1) * GAP
        for row in raw_rows:
            row.extend([""] * (columns - len(row)))
        weights = []
        for column in range(columns):
            lengths = sorted(len(re.sub("<[^>]+>", "", row[column])) for row in raw_rows)
            representative = lengths[min(len(lengths) - 1, int(.8 * len(lengths)))]
            weights.append(max(3, min(100, representative)) ** .8)
        minimum = min(24, width / columns / 2)
        widths = [minimum + (width - minimum * columns) * weight / sum(weights) for weight in weights]
        values = [[Paragraph(value or " ", cell_style) for value in row] for row in raw_rows]
        table = Table(values, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), .35, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            *spans,
        ]))
        table_records.append({"id": node.get("id"), "rows": len(values), "columns": columns, "reading_span": span})
        return table, span

    def image_info(node):
        parsed = urlparse(node.get("src", ""))
        if parsed.scheme not in ("", "file"):
            raise ValueError("Localize all article images before building the scroll")
        path = (Path(unquote(parsed.path)) if parsed.scheme == "file" else source.parent / unquote(parsed.path)).resolve(strict=True)
        with RasterImage.open(path) as raster:
            width, height = raster.size
        span = 2 if width / height > 1.8 else 1
        maximum_width = span * COLUMN_WIDTH + (span - 1) * GAP
        maximum_height = AVAILABLE_HEIGHT - 75
        factor = min(maximum_width / width, maximum_height / height)
        images.append({"source": str(path), "reading_span": span, "output_width_pt": width * factor, "output_height_pt": height * factor})
        return Image(str(path), width=width * factor, height=height * factor, hAlign="LEFT"), span

    def emit(node, forced_span=None):
        if isinstance(node, NavigableString):
            if str(node).strip():
                add(Paragraph(html.escape(str(node)), body), forced_span or 1)
            return
        if node.name in ("script", "style", "nav", "button") or "ltx_authors" in node.get("class", []):
            return
        if node.name == "figure":
            table = node.find("table")
            image = node.find("img")
            if table:
                flowable, span = make_table(table)
                figure_caption = node.find("figcaption")
                if figure_caption:
                    add(Paragraph(inline(figure_caption), caption), span)
                add(flowable, span)
            elif image:
                flowable, span = image_info(image)
                add(flowable, span)
                figure_caption = node.find("figcaption")
                if figure_caption:
                    add(Paragraph(inline(figure_caption), caption), span)
            else:
                for child in node.children:
                    emit(child, forced_span)
            return
        if node.name == "table":
            flowable, span = make_table(node)
            add(flowable, span)
            return
        if node.name == "img":
            flowable, span = image_info(node)
            add(flowable, span)
            return
        if node.name in ("p", "li", "figcaption", "dt", "dd", "pre"):
            add(Paragraph(inline(node), caption if node.name == "figcaption" else body), forced_span or 1)
            return
        if re.fullmatch("h[1-6]", node.name or ""):
            add(Paragraph(inline(node), heading), forced_span or 1)
            return
        for child in node.children:
            emit(child, forced_span)

    for child in article.children:
        emit(child)
    measuring_canvas = canvas.Canvas(io.BytesIO())
    panels = []
    current = None

    def new_panel(span):
        panel = {"span": span, "items": [], "y": TOP}
        panels.append(panel)
        return panel

    pending = deque(items)
    while pending:
        flowable, span = pending.popleft()
        if current is None or current["span"] != span:
            current = new_panel(span)
        width = span * COLUMN_WIDTH + (span - 1) * GAP
        available = current["y"] - BOTTOM
        _, height = flowable.wrapOn(measuring_canvas, width, available)
        reserve = body.leading * 2 if getattr(flowable, "keepWithNext", False) else 0
        if height + reserve <= available + .001:
            current["items"].append((flowable, current["y"] - height))
            current["y"] -= height + getattr(getattr(flowable, "style", None), "spaceAfter", 3)
            continue
        pieces = [] if reserve else flowable.splitOn(measuring_canvas, width, available)
        if pieces:
            pending.extendleft(reversed([(piece, span) for piece in pieces]))
            # A split fragment retains its exact height on the next iteration.
            if len(pieces) == 1 and current["items"]:
                current = new_panel(span)
            continue
        if not current["items"]:
            raise ValueError(f"A {type(flowable).__name__} cannot fit in an empty {span}-column panel")
        current = new_panel(span)
        pending.appendleft((flowable, span))
    panels = [panel for panel in panels if panel["items"]]
    max_slots = math.floor((2000 * mm - 2 * END_MARGIN + GAP) / (COLUMN_WIDTH + GAP))
    sections = []
    active = []
    slots = 0
    for panel in panels:
        if active and slots + panel["span"] > max_slots:
            sections.append(active)
            active, slots = [], 0
        active.append(panel)
        slots += panel["span"]
    if active:
        sections.append(active)
    combined = PdfWriter()
    records = []
    column = 1
    for number, section in enumerate(sections, 1):
        slots = sum(panel["span"] for panel in section)
        length = max(320 * mm, 2 * END_MARGIN + slots * COLUMN_WIDTH + (slots - 1) * GAP)
        path = output / f"article_scroll_section_{number:02d}.pdf"
        page = canvas.Canvas(str(path), pagesize=(ROLL_WIDTH, length), initialFontName="ArticleSans")
        page.setTitle(f"{arguments.title} - scroll section {number} of {len(sections)}")
        page.setAuthor(arguments.author)
        page.translate(0, length)
        page.rotate(-90)
        page.setLineWidth(.35)
        page.rect(12 * mm, 10 * mm, length - 24 * mm, ROLL_WIDTH - 20 * mm)
        x = END_MARGIN
        footers = []
        for panel in section:
            width = panel["span"] * COLUMN_WIDTH + (panel["span"] - 1) * GAP
            for flowable, y in panel["items"]:
                flowable.drawOn(page, x, y)
            label = f"Column {column}" if panel["span"] == 1 else f"Columns {column}-{column + panel['span'] - 1}"
            footers.append((x, label))
            x += width + GAP
            column += panel["span"]
        page.setFont("ArticleSans", 7)
        for x, label in footers:
            page.drawString(x, 12 * mm, label + f" | section {number}/{len(sections)}")
        page.showPage()
        page.save()
        combined.append(str(path))
        records.append({"number": number, "pdf": str(path), "width_mm": 215.9, "length_mm": round(length / mm, 6), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "status": "prepared"})
    combined_path = output / "article_scroll.pdf"
    with combined_path.open("wb") as stream:
        combined.write(stream)
    manifest = {
        "title": arguments.title, "author": arguments.author, "source_url": arguments.source_url,
        "license": arguments.license, "license_url": arguments.license_url,
        "created_at": datetime.now(timezone.utc).isoformat(), "source_html": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "body_font_pt": size,
        "leading_pt": body.leading, "column_width_mm": COLUMN_WIDTH / mm, "column_slots": column - 1,
        "reading_panels": len(panels), "sections": records, "figures": images, "tables": table_records,
        "estimated_paper_length_m": round(sum(record["length_mm"] for record in records) / 1000, 3),
        "combined_pdf": str(combined_path), "status": "prepared", "physical_output_confirmed": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in ("column_slots", "reading_panels", "estimated_paper_length_m", "combined_pdf")}, indent=2))
    print("Sections:", len(records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_html", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", default="", help="Optional source license metadata, when known")
    parser.add_argument("--license-url", default="", help="Optional source license URL, when known")
    parser.add_argument("--font-size", type=float, default=9)
    create_scroll(parser.parse_args())


if __name__ == "__main__":
    main()
