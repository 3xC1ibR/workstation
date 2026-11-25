"""Server-side markup for the review page, served reports, and proactive deliveries.

All content is escaped. Pages run only the service's own script files; data
reaches them through an inert JSON block. Content an agent builds (an
interactive document, or another application on the host) appears only inside
a sandboxed frame and is never written into these pages.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import interactive_documents
import markdown_text
from report_blocks import CONFIDENCE_LEVELS, REVERSIBILITY_LEVELS

ASSETS = Path(__file__).resolve().parents[1] / "assets"
WEB_LINK = re.compile(r"https?://[^\s]+\Z")
RIBBON_FIELD_LINK = re.compile(r"agentcoord://[^\s]+\Z")
PAGE_ROUTE = re.compile(r"/(?:(?:reports|operations)/[a-f0-9]{64}|deliveries/[a-f0-9]{64}(?:/attachments/[0-9]{1,2})?)?\Z")


class Addresses:
    """Decides where a link leads for the address a page is served on.

    `base` is the path prefix of this request, `public` the configured public
    address as (origin, host, prefix) or None, and `local_origins` the service's
    loopback origins. Targets inside the review page and other applications on
    the shared host stay in the same tab; everything else is left to the caller.
    """

    def __init__(self, base="", public=None, local_origins=()):
        self.base, self.public, self.local_origins = base, public, set(local_origins)

    def internal(self, target, item=None):
        """The same-tab address for a target on this host, or None.

        A page of the review page keeps its route under the current base.
        Another application on the public host opens in the embedded view,
        with `item` as the place to return to. A bare path is a local file,
        not an address, when it begins with a directory of this machine or
        ends in a file suffix other than .html; a full https address is never
        read as a file.
        """
        try:
            address = urlsplit(target)
        except ValueError:
            return None
        prefix, path = self.public[2] if self.public else "", address.path or "/"
        if address.scheme or address.netloc:
            origin = f"{address.scheme}://{address.netloc}"
            if origin in self.local_origins:
                prefix = ""
            elif not self.public or origin != self.public[0]:
                return None
            route = path[len(prefix):] or "/" if path == prefix or path.startswith(prefix + "/") else None
            local_file = False
        elif target.startswith("/") and not target.startswith("//"):
            route = path[len(prefix):] or "/" if prefix and (path == prefix or path.startswith(prefix + "/")) else path
            # A file of this machine: under one of its root directories, or named like a file rather than a page.
            local_file = (Path("/") / path.split("/")[1]).exists() or Path(path).suffix.lower() not in {"", ".html", ".htm"}
        else:
            return None
        if route is not None and PAGE_ROUTE.fullmatch(route) and not address.query:
            return self.base + route + ("#" + address.fragment if address.fragment else "")
        if not self.public or not prefix or local_file or address.query or address.fragment:
            return None
        try:
            interactive_documents.validate_address(path, prefix)
        except ValueError:
            return None
        return f"{self.base}/embedded?address={path}" + (f"&from={item}" if item else "")

    def on_this_host(self, target):
        """True for a full address on the public host or on this machine's own address."""
        try:
            address = urlsplit(target)
        except ValueError:
            return False
        origin = f"{address.scheme}://{address.netloc}"
        return origin in self.local_origins or bool(self.public) and origin == self.public[0]


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


OPERATION_ASKS = '<section id="operation-asks" class="context-asks" aria-label="Asks from this operation" hidden></section>'


def version_navigation(base, label, address, versions, current, controls=""):
    """Navigation above an item with versions: return link, version position, history, and an earlier-version notice.

    `versions` are newest first, each with id and received_at; `address` gives the path of one version from its
    position in that list and its identifier.
    """
    position = next(index for index, version in enumerate(versions) if version["id"] == current)
    number, total = len(versions) - position, len(versions)
    marked = ' aria-current="page"'
    history = "".join(
        f'<li><a href="{escape(base + address(index, version["id"]))}"{marked if version["id"] == current else ""}>'
        f'Version {len(versions) - index}</a> <span class="secondary">{moment_tag(version["received_at"])}</span></li>'
        for index, version in enumerate(versions))
    earlier = ("" if position == 0 else
               f'<p class="version-notice">You are reading version {number} of {total}, received {moment_tag(versions[position]["received_at"])}. '
               f'<a href="{escape(base + address(0, versions[0]["id"]))}">Open the latest version</a></p>')
    return (f'<nav class="page-navigation" aria-label="{label}"><a class="back-link" href="{escape(base)}/">Review</a>'
            f'<details class="version-history"><summary>Version {number} of {total}</summary><ol reversed>{history}</ol></details>'
            f'{controls}</nav>{earlier}')


def report_navigation(base, operation, report):
    """Navigation above a served report. The operation's asks are placed separately, under the report's title (OPERATION_ASKS)."""
    return version_navigation(base, "Report", lambda index, version: "/reports/" + version, operation["versions"], report,
                              '<button id="operation-dismiss" class="quiet" type="button" hidden></button>')


def delivery_route(series, version, latest):
    """The path of one version of a delivery. The latest version is the delivery's own address. An earlier one is
    named under its series, because a series continued with --replaces has the identifier of its first version."""
    return f"/deliveries/{version}" if latest else f"/deliveries/{series}?version={version}"


def embedded_frame(source, title):
    """The only way agent-built content enters a page: a frame without this page's origin or the right to navigate it.

    Of the browser's permissions the frame is given one, writing to the clipboard, so a document's own Copy control
    works. It cannot read the clipboard.
    """
    return (f'<iframe id="embedded-document" class="embedded-document" src="{escape(source)}" sandbox="{interactive_documents.SANDBOX}" '
            f'allow="{interactive_documents.PERMISSIONS}" referrerpolicy="no-referrer" loading="lazy" title="{escape(title)}"></iframe>')


def interactive_section(interactive, source, title, public_item, noun):
    """An item's interactive document inside its page, or where to read it when this address cannot show it.

    `source` is the frame address, or None for an application that is served only on the public address;
    `public_item` is this item's page there, when a public address is configured.
    """
    if source:
        content = embedded_frame(source, "Interactive document: " + title)
    else:
        link = f' <a href="{escape(public_item)}">Open this {noun} there</a>' if public_item else ""
        content = (f'<p class="note">This {noun} has an interactive document at <code>{escape(interactive["address"])}</code>, '
                   f'which is served on the tailnet address.{link}</p>')
    kind = " embedded-application" if interactive["kind"] == "address" else ""
    return f'<section class="embedded{kind}" aria-label="Interactive document">{content}</section>'


def link_item(link, addresses, delivery):
    label, target = escape(link["label"]), link["target"]
    name = Path(target).name
    if not WEB_LINK.match(target) and not RIBBON_FIELD_LINK.match(target) and name in delivery["attachments"]:
        return f'<li><a href="{escape(addresses.base)}/deliveries/{delivery["id"]}/attachments/{delivery["attachments"].index(name)}">{label}</a></li>'
    internal = addresses.internal(target, delivery["id"])
    if internal:                                           # another page here or another application on this host: the same tab
        return f'<li><a href="{escape(internal)}">{label}</a></li>'
    if WEB_LINK.match(target):                             # only another website opens a new tab
        opening = "" if addresses.on_this_host(target) else ' target="_blank"'
        return f'<li><a href="{escape(target)}"{opening} rel="noreferrer noopener">{label}</a></li>'
    if RIBBON_FIELD_LINK.match(target):
        return f'<li><a href="{escape(target)}">{label}</a> <span class="secondary">opens Ribbon Field</span></li>'
    return (f'<li>{label} <code class="local-path">{escape(target)}</code> '
            f'<button class="quiet copy-path" type="button" data-path="{escape(target)}">Copy path</button></li>')


def delivery_resolver(addresses, delivery):
    def resolve(target):
        if RIBBON_FIELD_LINK.match(target):
            return target
        if not WEB_LINK.match(target):
            name = Path(target.split("#")[0]).name
            if name in delivery["attachments"]:
                return f'{addresses.base}/deliveries/{delivery["id"]}/attachments/{delivery["attachments"].index(name)}'
        return addresses.internal(target, delivery["id"]) or (target if WEB_LINK.match(target) else None)
    return resolve


def origin_text(delivery):
    """The delivery's category, or the producing agent when it has none."""
    return escape(delivery.get("category") or delivery["origin"].get("agent") or "")


def without_repeated_title(body):
    """Drop a leading top-level heading; the page already shows the delivery title."""
    lines = body.lstrip().split("\n")
    return "\n".join(lines[1:]) if lines and re.match(r"#\s+\S", lines[0]) else body


def delivery_page(addresses, delivery, body, embedded="", public_url=None):
    """One version of a delivery. `embedded` is the markup of its interactive document, placed under the response panel."""
    base = addresses.base
    body = without_repeated_title(body) if body else body
    decision = delivery.get("decision") or {}
    recommendation = (f'<p class="recommendation"><strong>Recommended:</strong> {escape(delivery["recommended_default"])}</p>'
                      if delivery.get("recommended_default") else "")
    question = f'<p class="decision-question">{escape(decision["question"])}</p>' if decision else ""
    linked = {Path(link["target"]).name for link in delivery.get("links", [])} & set(delivery["attachments"])
    references = "".join(link_item(link, addresses, delivery) for link in delivery.get("links", [])) + "".join(
        f'<li><a href="{escape(base)}/deliveries/{delivery["id"]}/attachments/{index}">{escape(name)}</a></li>'
        for index, name in enumerate(delivery["attachments"]) if name not in linked)       # a linked attachment is listed once
    heading = ("Links and attachments" if delivery["attachments"] and delivery.get("links")
               else "Attachments" if delivery["attachments"] else "Links")
    version_address = lambda index, version: delivery_route(delivery["series"], version, index == 0)
    navigation = (version_navigation(base, "Delivery", version_address, delivery["versions"], delivery["id"]) if delivery["version_count"] > 1
                  else f'<nav class="page-navigation" aria-label="Delivery"><a class="back-link" href="{escape(base)}/">Review</a></nav>')
    packet_parts = []
    if delivery.get("reversibility"):
        word, tone = REVERSIBILITY_LEVELS[delivery["reversibility"]]
        note = f" ({escape(delivery['reversibility_note'])})" if delivery.get("reversibility_note") else ""
        packet_parts.append(f'<span><span class="decision-flag tone-{tone}">{word}</span>{note}</span>')
    if delivery.get("confidence"):
        word, tone = CONFIDENCE_LEVELS[delivery["confidence"]]
        basis = f": {escape(delivery['confidence_basis'])}" if delivery.get("confidence_basis") else ""
        packet_parts.append(f'<span><span class="tone-{tone}">{word}</span>{basis}</span>')
    packet_meta = f'<p class="sheet-meta packet-meta">{"".join(packet_parts)}</p>' if packet_parts else ""
    content = (
        f'{navigation}'
        f'<article class="sheet delivery"><header class="sheet-header"><h1>{escape(delivery["title"])}</h1>'
        f'<p class="sheet-meta">{f"<span>{origin_text(delivery)}</span>" if origin_text(delivery) else ""}{moment_tag(delivery["received_at"])}</p>'
        f'{packet_meta}</header>'
        f'<p class="assessment text">{escape(delivery["summary"])}</p>'
        f'<section class="response-panel" aria-label="Your response">{recommendation}{question}'
        f'<div id="delivery-response"><noscript><p class="note">Enable JavaScript to respond to this delivery.</p></noscript></div></section>'
        + embedded
        + (f'<section class="document">{markdown_text.render(body, delivery_resolver(addresses, delivery))}</section>' if body else "")
        + (f'<section><h2 class="section-heading">{heading}</h2><ul class="link-list">{references}</ul></section>' if references else "")
        + '</article>')
    configuration = {"delivery": {key: value for key, value in delivery.items() if key != "document_state"}}
    if delivery["interactive"]:
        configuration["embedded"] = {"kind": "delivery", "item": delivery["id"], "latest": delivery["latest"], "public_url": public_url}
    return document(delivery["title"], base, content,
                    ("controls.js", "delivery.js", "asks.js", "selection_messages.js") + (("embedded_host.js",) if delivery["interactive"] else ()),
                    configuration)


def attachment_page(addresses, delivery, name, content):
    base = addresses.base
    rendered = (markdown_text.render(content, delivery_resolver(addresses, delivery)) if name.lower().endswith((".md", ".markdown"))
                else f"<pre>{html.escape(content, quote=False)}</pre>")
    origin = delivery_route(delivery["series"], delivery["id"], delivery["latest"])
    body = (f'<nav class="page-navigation" aria-label="Attachment"><a class="back-link" href="{escape(base + origin)}">'
            f'{escape(delivery["title"])}</a></nav><article class="sheet delivery"><header class="sheet-header"><h1>{escape(name)}</h1></header>'
            f'<section class="document">{rendered}</section></article>')
    return document(name, base, body, ("controls.js", "delivery.js"), {"attachment": True})


def embedded_page(base, address, source, back, elsewhere, public_url=None, item=None):
    """The page frame around another application on this host.

    `source` is the frame address, or None on an address where the application is not served; `back` is
    (route, title) of the item the reader came from; `elsewhere` is this view on the public address. `item` is
    (kind, identifier, latest) when the application is that item's own interactive document: the view then keeps
    the item's saved document state, as the item's page does. Otherwise the view keeps no state.
    """
    route, label = back if back else ("/", "Review")
    if source:
        heading = f'<p class="sheet-meta"><a href="{escape(source)}">Open on its own</a></p>'
        content = embedded_frame(source, "Application at " + address)
    else:
        heading = ""
        link = f' <a href="{escape(elsewhere)}">Open it there</a>' if elsewhere else ""
        content = f'<p class="note">This application is served on the tailnet address.{link}</p>'
    body = (f'<nav class="page-navigation" aria-label="Embedded application"><a class="back-link" href="{escape(base)}{escape(route)}">{escape(label)}</a></nav>'
            f'<article class="sheet"><header class="sheet-header"><h1>{escape(address)}</h1>{heading}</header>'
            f'<section class="embedded embedded-application" aria-label="Application">{content}</section></article>')
    return document(address, base, body, ("controls.js", "embedded_host.js"),
                    {"embedded": {"kind": item[0] if item else None, "item": item[1] if item else None,
                                  "latest": bool(item and item[2]), "public_url": public_url}})
