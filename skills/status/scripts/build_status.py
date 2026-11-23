#!/usr/bin/env python3
"""Validate a status document and build a portable HTML report with in-page responses."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import html
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from status_fields import validate_fields


FIELDS = {
    "notices": ({"title", "text"}, set()),
    "metrics": ({"label", "value"}, {"detail", "source", "observed_at", "freshness_minutes"}),
    "actions": ({"action", "owner"}, {"reason", "status", "source"}),
    "sections": ({"title"}, {"text", "columns", "rows", "source", "observed_at", "freshness_minutes", "collapsed"}),
    "sources": ({"label", "location"}, {"observed_at"}),
}


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


def check_fields(record, required, optional, location):
    if not isinstance(record, dict):
        raise ValueError(f"{location} must be an object")
    missing = required - record.keys()
    extra = record.keys() - required - optional
    if missing or extra:
        raise ValueError(f"{location}: missing {sorted(missing)}; unknown {sorted(extra)}. "
                         "Represent additional information in sections or notices.")


def validate(document):
    required = {"title", "subject", "generated_at", "summary"}
    check_fields(document, required, set(FIELDS) | {"timezone", "response_fields"}, "report")
    validate_fields(document.get("response_fields", []))
    for key in required | ({"timezone"} & document.keys()):
        if not isinstance(document[key], str) or not document[key].strip():
            raise ValueError(f"{key} must be nonempty text")
    timestamp(document["generated_at"])
    ZoneInfo(document.get("timezone", "UTC"))
    for collection, (required_fields, optional) in FIELDS.items():
        records = document.get(collection, [])
        if not isinstance(records, list):
            raise ValueError(f"{collection} must be a list")
        for index, record in enumerate(records):
            location = f"{collection}[{index}]"
            check_fields(record, required_fields, optional, location)
            for key, value in record.items():
                if key in {"columns", "rows", "collapsed", "freshness_minutes"}:
                    continue
                if key == "value" and value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError(f"{location}.{key} must be text")
            for key in required_fields - {"value"}:
                if not record[key].strip():
                    raise ValueError(f"{location}.{key} cannot be empty")
            if "observed_at" in record:
                timestamp(record["observed_at"])
            if "freshness_minutes" in record:
                value = record["freshness_minutes"]
                if type(value) is not int or value < 0:
                    raise ValueError(f"{location}.freshness_minutes must be a nonnegative integer")
            if "collapsed" in record and type(record["collapsed"]) is not bool:
                raise ValueError(f"{location}.collapsed must be boolean")
            if "columns" in record or "rows" in record:
                columns, rows = record.get("columns"), record.get("rows")
                if not isinstance(columns, list) or not columns or not all(isinstance(c, str) and c for c in columns):
                    raise ValueError(f"{location}.columns must be a nonempty text list")
                if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(columns)
                        or not all(isinstance(cell, str) for cell in row) for row in rows):
                    raise ValueError(f"{location}.rows must match the columns and contain text cells")
            if collection == "sections" and not record.get("text") and "columns" not in record:
                raise ValueError(f"{location} requires text or a table")


def escape(value):
    return html.escape("Unknown" if value is None else str(value), quote=True)


WEB_ADDRESS = re.compile(r"(https?://[^\s<>\"')\]]+)")
NUMBERED_LINE = re.compile(r"\s*(\d{1,2}[.)])\s+(.*)\Z")


def linked(value):
    """Escaped text with its web addresses made into links."""
    parts = []
    for index, part in enumerate(WEB_ADDRESS.split(value)):
        if index % 2 == 0:
            parts.append(escape(part))
            continue
        address = part.rstrip(".,;:")
        shown = escape(address).replace("/", "/<wbr>").replace(":/<wbr>/<wbr>", "://")     # a long address breaks after a slash
        parts.append(f'<a href="{escape(address)}" rel="noreferrer noopener">{shown}</a>{escape(part[len(address):])}')
    return "".join(parts)


def prose(value):
    """The author's text for a `text` block: addresses linked, and each numbered line set as a step with a hanging indent."""
    output, plain = [], []
    for line in value.split("\n"):
        step = NUMBERED_LINE.match(line)
        if step:
            if plain:
                output.append(linked("\n".join(plain)))
                plain = []
            output.append(f'<span class="step"><span>{escape(step.group(1))}</span><span>{linked(step.group(2))}</span></span>')
        else:
            plain.append(line)
    if plain:
        output.append(linked("\n".join(plain)))
    return "".join(output)


def response_script(document, connection):
    assets = Path(__file__).resolve().parents[1] / "assets"
    configuration = json.dumps({"fields": document["response_fields"], "connection": connection}, ensure_ascii=True).replace("<", "\\u003c")
    return ("(() => {\nconst embeddedConfiguration = " + configuration + ";\n" +
            "\n".join((assets / name).read_text() for name in ("controls.js", "responses.js", "report.js")) + "\n})();")


def response_policy(document, connection):
    """Content policy for a portable report: only its exact embedded script may run."""
    digest = base64.b64encode(hashlib.sha256(response_script(document, connection).encode()).digest()).decode()
    origin = " ".join(["'self'"] + ([urlsplit(connection["url"]).scheme + "://" + urlsplit(connection["url"]).netloc] if connection else []))
    return (f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; img-src data:; "
            f"connect-src {origin}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def render(document, connection=None, *, page=None):
    """Build the report sheet.

    Without `page` the result is a portable file with its style and response
    editor embedded. The Status service passes `page` (base path, navigation
    markup, markup to place under the header, and a configuration object) to
    serve the same sheet with shared assets and its own navigation. Its
    `after_responses` markup holds the sandboxed frame of an interactive
    document, placed after the assessment, notices, metrics and response
    fields; its `resolve` function keeps source addresses on this host inside
    the page.
    """
    validate(document)
    generated = timestamp(document["generated_at"])
    zone = ZoneInfo(document.get("timezone", "UTC"))

    def time_text(value, full=True):
        local = timestamp(value).astimezone(zone)
        clock = f"{local.hour % 12 or 12}:{local:%M} {local:%p}"
        if full:
            return f"{local:%b} {local.day}, {local.year}, {clock} {local:%Z}"
        # Inside the report the header already states the year and timezone.
        year = "" if local.year == generated.astimezone(zone).year else f", {local.year}"
        return f"{local:%b} {local.day}{year}, {clock}"

    def provenance(record):
        parts = []
        if record.get("source"):
            parts.append(escape(record["source"]))
        observed = record.get("observed_at")
        if observed:
            parts.append(escape(time_text(observed, full=False)))
        state = ""
        if "freshness_minutes" in record:
            if not observed:
                state = "Observation time unknown"
            else:
                age = (generated - timestamp(observed)).total_seconds()
                if age < -60:
                    state = "Observed after the report: verify clock"
                elif age > record["freshness_minutes"] * 60:
                    state = "Stale"
        if state:
            parts.append(f'<span class="freshness">{escape(state)}</span>')
        return '<div class="provenance">' + " · ".join(parts) + "</div>" if parts else ""

    def table(section):
        if "columns" not in section:
            return ""
        if not section["rows"]:
            return '<p class="empty">No records available.</p>'
        # A table of two columns wraps at phone width; wider tables scroll sideways under their first column.
        pair = len(section["columns"]) <= 2
        # A column is given room for its longest cell, so a scrolling table never wraps to a word a line.
        longest = [max(len(row[index]) for row in section["rows"]) for index in range(len(section["columns"]))]
        classes = ["" if pair or index == 0 or length <= 20 else ' class="text-column"' if length > 70 else ' class="phrase-column"'
                   for index, length in enumerate(longest)]
        heading = "".join(f'<th scope="col"{classes[index]}>{escape(column)}</th>' for index, column in enumerate(section["columns"]))
        rows = "".join("<tr>" + "".join(f"<td{classes[index]}>{escape(cell)}</td>" for index, cell in enumerate(row)) + "</tr>" for row in section["rows"])
        if pair:
            return f'<div class="table-region table-region-narrow"><table class="table-pair"><thead><tr>{heading}</tr></thead><tbody>{rows}</tbody></table></div>'
        return (f'<div class="table-region" tabindex="0" role="region" aria-label="{escape(section["title"])}">'
                f'<table><thead><tr>{heading}</tr></thead><tbody>{rows}</tbody></table></div>')

    def source_link(location):
        address = urlsplit(location)
        if address.scheme in {"http", "https"} and address.netloc:
            destination = page["resolve"](location) if page and page.get("resolve") else None
            return f'<a href="{escape(destination or location)}" rel="noreferrer">{escape(location)}</a>'
        return f"<code>{escape(location)}</code>"

    assets = Path(__file__).resolve().parents[1] / "assets"
    # One quiet line under the title: the subject, then when the observations were assembled. A long subject folds away.
    # A served page is rendered when it is read, so it can leave out the current year; a portable file states it.
    current = bool(page) and generated.astimezone(zone).year == datetime.now(zone).year
    assembled = f'As of {escape(time_text(document["generated_at"], full=not current))} {escape(generated.astimezone(zone).strftime("%Z")) if current else ""}'.rstrip()
    subject = f'<p class="sheet-meta"><span class="subject">{escape(document["subject"])}</span><span>{assembled}</span></p>'
    if len(document["subject"]) > 100:
        subject = (f'<details class="subject-details"><summary>{escape(document["subject"][:60])}… (show the full subject)</summary>'
                   f'<p class="subject">{escape(document["subject"])}</p></details><p class="sheet-meta"><span>{assembled}</span></p>')
    if page:
        base = escape(page["base"])
        head = (f'<link rel="stylesheet" href="{base}/tokens.css"><link rel="stylesheet" href="{base}/style.css">'
                f'<link rel="stylesheet" href="{base}/review.css">'
                + "".join(f'<script src="{base}/{escape(name)}" defer></script>' for name in page["scripts"]))
    else:
        head = f'<style>{(assets / "tokens.css").read_text()}{(assets / "style.css").read_text()}</style>'
    root = f' data-base="{escape(page["base"])}"' if page else ""
    output = [f'<!doctype html><html lang="en"{root}><head><meta charset="utf-8">'
              f'<meta name="viewport" content="width=device-width, initial-scale=1">'
              f'<title>{escape(document["title"])}</title>{head}</head><body><main>',
              page["navigation"] if page else "",
              f'<article class="sheet"><header class="sheet-header"><h1>{escape(document["title"])}</h1>{subject}</header>',
              # The opening: what needs the reader and the assessment lead; on a wide page the measures stand beside them.
              '<div class="sheet-opening"><div class="sheet-lead">',
              page.get("after_header", "") if page else ""]
    output.append(f'<p class="assessment text">{prose(document["summary"])}</p>')
    for notice in document.get("notices", []):
        output.append(f'<aside class="notice"><h2>{escape(notice["title"])}</h2><p class="text">{prose(notice["text"])}</p></aside>')
    output.append('</div>')
    if document.get("metrics"):
        output.append('<dl class="metrics">')
        for metric in document["metrics"]:
            detail = f'<dd class="detail text">{escape(metric["detail"])}</dd>' if metric.get("detail") else ""
            source = f'<dd>{provenance(metric)}</dd>' if provenance(metric) else ""
            output.append(f'<div class="metric"><dt>{escape(metric["label"])}</dt><dd class="value">{escape(metric["value"])}</dd>{detail}{source}</div>')
        output.append('</dl>')
    output.append('</div>')
    if document.get("response_fields"):
        output.append('<section id="status-response-fields"><h2 class="section-heading">Your responses</h2>'
                      '<noscript><p>Enable JavaScript to edit and save responses in this page.</p><dl class="response-questions">')
        for field in document["response_fields"]:
            output.append(f'<dt>{escape(field["label"])}{" · Required" if field.get("required") else ""}</dt>'
                          f'<dd class="text">{escape(field.get("help", ""))}</dd>')
            if field["type"] == "choice":
                output.append(f'<dd class="text">Choices: {escape(" / ".join(field["options"]))}</dd>')
        output.append('</dl></noscript></section>')
    if page and page.get("after_responses"):
        output.append(page["after_responses"])
    if document.get("actions"):
        output.append('<section><h2 class="section-heading">Next actions</h2><ol class="actions">')
        for action in document["actions"]:
            reason = f'<p class="text">{prose(action["reason"])}</p>' if action.get("reason") else ""
            status = action.get("status", "status not stated")
            state = ("settled" if status.lower().startswith(("done", "complete", "finished", "closed", "cancel"))
                     else "blocked" if "block" in status.lower() else "open")
            output.append(f'<li data-status="{state}"><p class="action-title">{escape(action["action"])}</p>'
                          f'<p class="action-owner">{escape(action["owner"])} · <span class="action-status">{escape(status)}</span></p>'
                          f'{reason}{provenance(action)}</li>')
        output.append('</ol></section>')
    for section in document.get("sections", []):
        heading = escape(section["title"])
        if section.get("collapsed"):
            output.append(f'<details><summary>{heading}</summary>')
        else:
            output.append(f'<section><h2 class="section-heading">{heading}</h2>')
        text = f'<p class="text">{prose(section["text"])}</p>' if section.get("text") else ""
        output.append(f'{text}{table(section)}{provenance(section)}')
        output.append('</details>' if section.get("collapsed") else '</section>')
    if document.get("sources"):
        output.append('<details><summary>Sources</summary>')
        for source in document["sources"]:
            output.append(f'<div class="source"><p>{escape(source["label"])}</p>{source_link(source["location"])}{provenance(source)}</div>')
        output.append('</details>')
    output.append('</article>')
    if page:
        configuration = json.dumps(page["configuration"], ensure_ascii=True).replace("<", "\\u003c")
        output.append(f'<script type="application/json" id="status-configuration">{configuration}</script>')
    output.append('</main>')
    if document.get("response_fields") and not page:
        output.append('<script>' + response_script(document, connection) + '</script>')
    output.append('</body></html>')
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace", default=os.getcwd(), help="Origin workspace shown in the shared Status inbox")
    parser.add_argument("--agent", help="Stable agent name, when known")
    parser.add_argument("--provider", help="Producing provider, when known")
    parser.add_argument("--thread-id", default=os.environ.get("AGENT_COORD_SESSION_ID") or os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--operation", help="Stable operation key; later reports with the same key become new versions of one living report. "
                        "Defaults to the workspace with the agent name, then the conversation.")
    parser.add_argument("--no-register", action="store_true", help="Build a preview or test fixture without adding it to the inbox")
    parser.add_argument("--viewer-url", default=os.environ.get("AGENT_STATUS_URL", "http://127.0.0.1:8766"), help="Local Status service used by the portable page's response editor")
    from register_status import add_interactive_arguments, inbox_directory, interactive_arguments, register
    add_interactive_arguments(parser)
    args = parser.parse_args()
    if args.no_register and (args.interactive or args.embed):
        parser.error("--interactive and --embed belong to the registered report; they have no effect with --no-register.")
    try:
        document = json.loads(args.document.read_text(encoding="utf-8"))
        result = render(document)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print(args.output.resolve())
    if not args.no_register:
        try:
            identifier = register(document, result, workspace=args.workspace, agent=args.agent,
                                  provider=args.provider, thread_id=args.thread_id, viewer_url=args.viewer_url,
                                  operation=args.operation, **interactive_arguments(args, inbox_directory()))
        except (ValueError, OSError) as error:
            parser.error(str(error))
        if document.get("response_fields"):
            from response_access import connection
            result = render(document, connection(inbox_directory(), identifier, args.viewer_url))
            args.output.write_text(result, encoding="utf-8")
        print(f"Status inbox receipt: {identifier}")
        # Lead with the address that opens on every device; the address on this Mac is the fallback.
        from status_server import DEFAULT_PORT, saved_public_url
        public, local = saved_public_url(inbox_directory()), f"http://127.0.0.1:{DEFAULT_PORT}/reports/{identifier}"
        if public:
            print(f"Review page: {public}/reports/{identifier}")
            print(f"Review page (this Mac only): {local}")
        else:
            print(f"Review page: {local}")


if __name__ == "__main__":
    main()
