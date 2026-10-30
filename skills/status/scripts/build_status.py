#!/usr/bin/env python3
"""Validate a status document and build one offline HTML engineering sheet."""
from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


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
    check_fields(document, required, set(FIELDS) | {"timezone"}, "report")
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


def render(document):
    validate(document)
    generated = timestamp(document["generated_at"])
    zone = ZoneInfo(document.get("timezone", "UTC"))

    def time_text(value):
        return timestamp(value).astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")

    def provenance(record):
        parts = []
        if record.get("source"):
            parts.append(escape(record["source"]))
        observed = record.get("observed_at")
        if observed:
            parts.append("Observed " + escape(time_text(observed)))
        state = ""
        if "freshness_minutes" in record:
            if not observed:
                state = "OBSERVATION TIME UNKNOWN"
            else:
                age = (generated - timestamp(observed)).total_seconds()
                if age < -60:
                    state = "OBSERVATION TIME AHEAD OF REPORT — VERIFY CLOCK"
                elif age > record["freshness_minutes"] * 60:
                    state = "LAST KNOWN — REFRESH NEEDED"
        if state:
            parts.append(f'<span class="freshness">{escape(state)}</span>')
        return '<div class="provenance">' + " · ".join(parts) + "</div>" if parts else ""

    def table(section):
        if "columns" not in section:
            return ""
        if not section["rows"]:
            return '<p class="empty">No records available.</p>'
        classes = [' class="text-column"' if index > 0 and any(len(row[index]) > 70 for row in section["rows"]) else ""
                   for index in range(len(section["columns"]))]
        heading = "".join(f'<th scope="col"{classes[index]}>{escape(column)}</th>' for index, column in enumerate(section["columns"]))
        rows = "".join("<tr>" + "".join(f"<td{classes[index]}>{escape(cell)}</td>" for index, cell in enumerate(row)) + "</tr>" for row in section["rows"])
        return (f'<p class="scroll-note">Scroll table horizontally for all columns →</p>'
                f'<div class="table-region" tabindex="0" role="region" aria-label="{escape(section["title"])}">'
                f'<table><thead><tr>{heading}</tr></thead><tbody>{rows}</tbody></table></div>')

    def source_link(location):
        address = urlsplit(location)
        if address.scheme in {"http", "https"} and address.netloc:
            return f'<a href="{escape(location)}" rel="noreferrer">{escape(location)}</a>'
        return f"<code>{escape(location)}</code>"

    style = (Path(__file__).resolve().parents[1] / "assets/style.css").read_text()
    subject = f'<p class="subject">{escape(document["subject"])}</p>'
    if len(document["subject"]) > 100:
        subject = (f'<details class="subject-details"><summary>{escape(document["subject"][:60])}… — expand subject</summary>'
                   f'<p class="subject">{escape(document["subject"])}</p></details>')
    output = [f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
              f'<meta name="viewport" content="width=device-width, initial-scale=1">'
              f'<title>{escape(document["title"])}</title><style>{style}</style></head><body><main>',
              f'<header><div><h1>{escape(document["title"])}</h1>{subject}</div>'
              f'<p class="meta">STATUS SHEET<br>Generated {escape(time_text(document["generated_at"]))}<br>Offline snapshot</p></header>']
    for notice in document.get("notices", []):
        output.append(f'<aside class="notice"><h2>{escape(notice["title"])}</h2><p class="text">{escape(notice["text"])}</p></aside>')
    output.append(f'<p class="assessment text">{escape(document["summary"])}</p>')
    if document.get("metrics"):
        output.append('<dl class="metrics">')
        for metric in document["metrics"]:
            output.append(f'<div class="metric"><dt>{escape(metric["label"])}</dt><dd class="value">{escape(metric["value"])}</dd>'
                          f'<dd class="detail text">{escape(metric.get("detail", ""))}</dd><dd>{provenance(metric)}</dd></div>')
        output.append('</dl>')
    number = 0
    if document.get("actions"):
        number += 1
        output.append(f'<section><h2 class="section-heading"><span class="reference">{number:02d}</span>Next actions</h2><ol class="actions">')
        for action in document["actions"]:
            output.append(f'<li><p class="action-title">{escape(action["action"])}</p>'
                          f'<p class="label">{escape(action["owner"])} · {escape(action.get("status", "unspecified"))}</p>'
                          f'<p class="text">{escape(action.get("reason", ""))}</p>{provenance(action)}</li>')
        output.append('</ol></section>')
    for section in document.get("sections", []):
        number += 1
        heading = f'<span class="reference">{number:02d}</span> {escape(section["title"])}'
        if section.get("collapsed"):
            output.append(f'<details><summary>{heading}</summary>')
        else:
            output.append(f'<section><h2 class="section-heading">{heading}</h2>')
        output.append(f'<p class="text">{escape(section.get("text", ""))}</p>{table(section)}{provenance(section)}')
        output.append('</details>' if section.get("collapsed") else '</section>')
    if document.get("sources"):
        output.append('<details><summary>Source record</summary>')
        for source in document["sources"]:
            output.append(f'<div class="source"><p>{escape(source["label"])}</p>{source_link(source["location"])}{provenance(source)}</div>')
        output.append('</details>')
    output.append('<footer><span>STATUS / ENGINEERING RECORD</span><span>Source observation times govern freshness.</span></footer></main></body></html>')
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace", default=os.getcwd(), help="Origin workspace shown in the shared Status inbox")
    parser.add_argument("--agent", help="Stable agent name, when known")
    parser.add_argument("--provider", help="Producing provider, when known")
    parser.add_argument("--thread-id", default=os.environ.get("AGENT_COORD_SESSION_ID") or os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--no-register", action="store_true", help="Build a preview or test fixture without adding it to the inbox")
    args = parser.parse_args()
    try:
        document = json.loads(args.document.read_text(encoding="utf-8"))
        result = render(document)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print(args.output.resolve())
    if not args.no_register:
        from register_status import register
        identifier = register(document, result, workspace=args.workspace, agent=args.agent,
                              provider=args.provider, thread_id=args.thread_id)
        print(f"Status inbox receipt: {identifier}")


if __name__ == "__main__":
    main()
