#!/usr/bin/env python3
"""Validate an exploration document and compile a portable HTML artifact."""
import argparse
import datetime as dt
import html
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def validate(document):
    errors = []
    if not isinstance(document, dict): return ["Document must be an object"]
    if document.get("version") != 1: errors.append("version must be 1")
    for name in ["id", "title"]:
        if not isinstance(document.get(name), str) or not document[name].strip(): errors.append(f"{name} must be nonempty text")
    dataset = document.get("dataset", {})
    if not isinstance(dataset, dict): return errors + ["dataset must be an object"]
    fields = dataset.get("fields", [])
    if not isinstance(fields, list) or not fields: return errors + ["dataset.fields must be a nonempty array"]
    if any(not isinstance(field, dict) or not isinstance(field.get("key"), str) for field in fields): return errors + ["Fields must have string keys"]
    schema = {field["key"]: field for field in fields}
    if len(schema) != len(fields): errors.append("Field keys must be unique")
    for field in fields:
        if field.get("type") not in ["number", "date", "string", "boolean"]: errors.append(f"Unknown type for {field['key']}")
    for key in ["entityKey", "labelKey"]:
        if dataset.get(key) not in schema: errors.append(f"dataset.{key} must name a field")
    time = document.get("time")
    if time:
        if time.get("field") not in schema or schema[time["field"]].get("type") not in ["number", "date"]: errors.append("time.field must name a numeric or date field")
        if time.get("mode") not in ["snapshot", "cumulative"]: errors.append("time.mode must be snapshot or cumulative")
    rows = dataset.get("rows", [])
    if not isinstance(rows, list): return errors + ["dataset.rows must be an array"]
    identities = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict): errors.append(f"Row {index} must be an object"); continue
        unknown = set(row) - set(schema)
        if unknown: errors.append(f"Row {index} has undeclared fields: {sorted(unknown)}")
        for key, value in row.items():
            if key not in schema or value is None: continue
            kind = schema[key].get("type")
            valid = True
            if kind == "number": valid = isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)
            elif kind == "boolean": valid = isinstance(value,bool)
            elif kind == "string": valid = isinstance(value,str)
            elif kind == "date":
                try: dt.datetime.fromisoformat(value.replace("Z", "+00:00")); valid = bool(re.match(r"^\d{4}-\d\d-\d\d", value))
                except (ValueError,TypeError,AttributeError): valid = False
            if not valid: errors.append(f"Row {index} field {key} is not a valid {kind}")
        identity = row.get(dataset.get("entityKey"))
        stamp = row.get(time["field"]) if time else None
        if identity is None: errors.append(f"Row {index} lacks entity identity")
        if time and stamp is None: errors.append(f"Row {index} lacks observed time")
        signature = (json.dumps(identity,sort_keys=True),json.dumps(stamp,sort_keys=True))
        if signature in identities: errors.append(f"Duplicate entity/time identity at row {index}")
        identities.add(signature)
    views = document.get("views", [])
    if not isinstance(views,list) or not views: errors.append("views must be a nonempty array"); views=[]
    view_ids = set()
    for view in views:
        if not isinstance(view,dict): errors.append("Views must be objects"); continue
        if not isinstance(view.get("id"),str) or view.get("id") in view_ids: errors.append("View IDs must be unique strings")
        view_ids.add(view.get("id"))
        if view.get("type") not in ["scatter","line","bar","histogram","table"]: errors.append(f"Unknown view type: {view.get('type')}")
        for key in ["x","y","color","size","series","low","high"]:
            if key in view and view[key] not in schema: errors.append(f"View {view.get('id')} references unknown {key} field")
        if view.get("type") in ["scatter","line"] and not all(k in view for k in ["x","y"]): errors.append("Scatter and line views require x and y")
        for axis in ["x","y"]:
            scale = view.get(axis+"Scale")
            if scale and scale not in ["linear","log","sqrt","symlog","utc","point"]: errors.append(f"Unknown {axis} scale")
            domain = view.get(axis+"Domain")
            if domain is not None and (not isinstance(domain,list) or len(domain)!=2): errors.append(f"{axis}Domain must contain two bounds")
    for filter_ in document.get("filters",[]):
        if filter_.get("field") not in schema: errors.append("Filter references an unknown field")
    for source in dataset.get("sources",[]):
        if source.get("url") and urlparse(source["url"]).scheme not in ["http","https"]: errors.append("Source URLs must use HTTP or HTTPS")
    for link in document.get("links",[]):
        href=link.get("href","")
        if urlparse(href).scheme not in ["","http","https"] or href.startswith("//"): errors.append("Links must be relative, HTTP or HTTPS")
    # The exact browser validator is the final authority, so a document accepted
    # by this compiler cannot fail later merely because the two schemas drift.
    if not errors:
        try:
            check = subprocess.run(["node", "-e", "const fs=require('node:fs');try{require(process.argv[1]).validate(JSON.parse(fs.readFileSync(0,'utf8')))}catch(e){process.stderr.write(e.message);process.exit(1)}", str(ROOT/"assets/core.js")],input=json.dumps(document,allow_nan=False),text=True,capture_output=True,timeout=30)
            if check.returncode: errors.append(check.stderr.strip() or "Runtime validation failed")
        except FileNotFoundError: errors.append("Node.js is required to run the shared browser schema validator")
        except subprocess.TimeoutExpired: errors.append("Runtime schema validation exceeded 30 seconds")
    return errors


def build(document):
    errors = validate(document)
    if errors: raise ValueError("\n".join(errors[:30]))
    css = (ROOT/"assets/style.css").read_text()
    scripts = ["vendor/d3.min.js", "vendor/plot.umd.min.js", "core.js", "runtime.js"]
    javascript = "\n".join((ROOT/"assets"/name).read_text() for name in scripts)
    if re.search(r"</script", javascript, re.I): raise ValueError("Runtime contains an unsafe script terminator")
    data = json.dumps(document,ensure_ascii=False,allow_nan=False,separators=(",",":")).replace("<","\\u003c").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
    title = html.escape(document["title"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{html.escape(document.get('subtitle',''),quote=True)}"><title>{title}</title>
<style id="data-exploration-style">{css}</style>
<style>body{{margin:0;background:#f7f6f2}}noscript{{display:block;padding:2rem;font:16px sans-serif}}</style></head>
<body><noscript>This interactive exploration requires JavaScript. The accompanying observations.csv contains the source observations.</noscript>
<main id="exploration"></main><script id="exploration-document" type="application/json">{data}</script>
<script>{javascript}
window.exploration = DataExploration.create(document.getElementById("exploration"), JSON.parse(document.getElementById("exploration-document").textContent));
</script></body></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("-o","--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args=parser.parse_args()
    try:
        document=json.loads(args.document.read_text())
        errors=validate(document)
        if errors: raise ValueError("\n".join(errors[:30]))
        if args.validate_only: print(f"Valid: {len(document['dataset']['rows'])} observations, {len(document['views'])} views"); return 0
        if args.output is None: parser.error("--output is required unless --validate-only")
        result=build(document); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(result)
        print(f"Built {args.output} ({len(result.encode()):,} bytes; offline dependencies embedded)")
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error: print(str(error),file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
