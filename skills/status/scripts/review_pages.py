"""Server-side markup for the review page, served reports, and proactive deliveries.

All content is escaped. Pages run only the service's own script files; data
reaches them through an inert JSON block.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re

import markdown_text

ASSETS = Path(__file__).resolve().parents[1] / "assets"
WEB_LINK = re.compile(r"https?://[^\s]+\Z")
RIBBON_FIELD_LINK = re.compile(r"agentcoord://[^\s]+\Z")


def escape(value):
    return html.escape(str(value), quote=True)


def data_block(value):
    return ('<script type="application/json" id="status-configuration">'
            + json.dumps(value, ensure_ascii=True).replace("<", "\\u003c") + "</script>")


def moment_tag(value):
    """A timestamp the page script rewrites in the reader's own timezone."""
    return f'<time datetime="{escape(value)}">{escape(value[:16].replace("T", " "))} UTC</time>'


def review_page(base):
    return (ASSETS / "review.html").read_text(encoding="utf-8").replace("{{base}}", escape(base))


def document(title, base, body, scripts, configuration=None):
    tags = "".join(f'<script src="{escape(base)}/{name}" defer></script>' for name in scripts)
    return (f'<!doctype html><html lang="en" data-base="{escape(base)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title>'
            f'<link rel="stylesheet" href="{escape(base)}/tokens.css"><link rel="stylesheet" href="{escape(base)}/style.css">'
            f'<link rel="stylesheet" href="{escape(base)}/review.css">'
            f'{tags}</head><body><main>{body}{data_block(configuration) if configuration is not None else ""}</main></body></html>')


def report_navigation(base, operation, report):
    """Navigation above a served report: return link, version position, and history."""
    versions = operation["versions"]                       # newest first
    position = next(index for index, version in enumerate(versions) if version["id"] == report)
    number, total, latest = len(versions) - position, len(versions), position == 0
    current = ' aria-current="page"'
    history = "".join(
        f'<li><a href="{escape(base)}/reports/{version["id"]}"{current if version["id"] == report else ""}>'
        f'Version {len(versions) - index}</a> <span class="secondary">{moment_tag(version["received_at"])}</span></li>'
        for index, version in enumerate(versions))
    earlier = ("" if latest else
               f'<p class="version-notice">You are reading version {number} of {total}, received {moment_tag(versions[position]["received_at"])}. '
               f'<a href="{escape(base)}/reports/{versions[0]["id"]}">Open the latest version</a></p>')
    return (f'<nav class="page-navigation" aria-label="Report"><a class="back-link" href="{escape(base)}/">Review</a>'
            f'<details class="version-history"><summary>Version {number} of {total}</summary><ol reversed>{history}</ol></details>'
            f'<button id="operation-dismiss" class="quiet" type="button" hidden></button></nav>'
            f'{earlier}<section id="operation-asks" class="context-asks" aria-label="Asks from this operation" hidden></section>')


def link_item(link, base, delivery):
    label, target = escape(link["label"]), link["target"]
    if WEB_LINK.match(target):
        return f'<li><a href="{escape(target)}" target="_blank" rel="noreferrer noopener">{label}</a></li>'
    if RIBBON_FIELD_LINK.match(target):
        return f'<li><a href="{escape(target)}">{label}</a> <span class="secondary">opens Ribbon Field</span></li>'
    name = Path(target).name
    if name in delivery["attachments"]:
        return f'<li><a href="{escape(base)}/deliveries/{delivery["id"]}/attachments/{delivery["attachments"].index(name)}">{label}</a></li>'
    return (f'<li>{label} <code class="local-path">{escape(target)}</code> '
            f'<button class="quiet copy-path" type="button" data-path="{escape(target)}">Copy path</button></li>')


def delivery_resolver(base, delivery):
    def resolve(target):
        if WEB_LINK.match(target) or RIBBON_FIELD_LINK.match(target):
            return target
        name = Path(target.split("#")[0]).name
        if name in delivery["attachments"]:
            return f'{base}/deliveries/{delivery["id"]}/attachments/{delivery["attachments"].index(name)}'
        return None
    return resolve


def origin_text(delivery):
    origin = delivery["origin"]
    return " · ".join(escape(part) for part in (delivery.get("category"), origin.get("agent"), Path(origin.get("workspace") or "").name) if part)


def without_repeated_title(body):
    """Drop a leading top-level heading; the page already shows the delivery title."""
    lines = body.lstrip().split("\n")
    return "\n".join(lines[1:]) if lines and re.match(r"#\s+\S", lines[0]) else body


def delivery_page(base, delivery, body):
    body = without_repeated_title(body) if body else body
    decision = delivery.get("decision") or {}
    recommendation = (f'<p class="recommendation"><strong>Recommended:</strong> {escape(delivery["recommended_default"])}</p>'
                      if delivery.get("recommended_default") else "")
    question = f'<p class="decision-question">{escape(decision["question"])}</p>' if decision else ""
    linked = {Path(link["target"]).name for link in delivery.get("links", [])} & set(delivery["attachments"])
    references = "".join(link_item(link, base, delivery) for link in delivery.get("links", [])) + "".join(
        f'<li><a href="{escape(base)}/deliveries/{delivery["id"]}/attachments/{index}">{escape(name)}</a></li>'
        for index, name in enumerate(delivery["attachments"]) if name not in linked)       # a linked attachment is listed once
    heading = ("Links and attachments" if delivery["attachments"] and delivery.get("links")
               else "Attachments" if delivery["attachments"] else "Links")
    content = (
        f'<nav class="page-navigation" aria-label="Delivery"><a class="back-link" href="{escape(base)}/">Review</a></nav>'
        f'<article class="sheet delivery"><header class="sheet-header"><h1>{escape(delivery["title"])}</h1>'
        f'<p class="sheet-meta">{origin_text(delivery)}{" · " if origin_text(delivery) else ""}Delivered {moment_tag(delivery["received_at"])}</p></header>'
        f'<p class="assessment text">{escape(delivery["summary"])}</p>'
        f'<section class="decision-panel" aria-label="Your response">{recommendation}{question}'
        f'<div id="delivery-response"><noscript><p class="note">Enable JavaScript to respond to this delivery.</p></noscript></div></section>'
        + (f'<section class="document">{markdown_text.render(body, delivery_resolver(base, delivery))}</section>' if body else "")
        + (f'<section><h2 class="section-heading">{heading}</h2><ul class="link-list">{references}</ul></section>' if references else "")
        + '</article>')
    return document(delivery["title"], base, content, ("controls.js", "delivery.js"), {"delivery": delivery})


def attachment_page(base, delivery, name, content):
    rendered = (markdown_text.render(content, delivery_resolver(base, delivery)) if name.lower().endswith((".md", ".markdown"))
                else f"<pre>{html.escape(content, quote=False)}</pre>")
    body = (f'<nav class="page-navigation" aria-label="Attachment"><a class="back-link" href="{escape(base)}/deliveries/{delivery["id"]}">'
            f'{escape(delivery["title"])}</a></nav><article class="sheet delivery"><header class="sheet-header"><h1>{escape(name)}</h1></header>'
            f'<section class="document">{rendered}</section></article>')
    return document(name, base, body, ("controls.js", "delivery.js"), {"attachment": True})
