#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb==1.4.3", "openpyxl==3.1.5", "xlrd==2.0.2", "pyarrow==22.0.0"]
# ///
"""Import common local data formats into a typed exploration; never upload data."""
import argparse
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys


def scalar(value):
    if isinstance(value,dt.datetime):
        if value.tzinfo is None and value.time()==dt.time(0): return value.date().isoformat()
        return value.isoformat()
    if isinstance(value,dt.date): return value.isoformat()
    if isinstance(value,Decimal): return float(value)
    if isinstance(value,float) and not math.isfinite(value): return None
    if isinstance(value,(dict,list)): return json.dumps(value,ensure_ascii=False,allow_nan=False)
    if value is None or isinstance(value,(str,int,float,bool)): return value
    raise ValueError(f"Unsupported field type: {type(value).__name__}")


def read_rows(path, format_=None, table=None, sheet=None, records_path=None, encoding="utf-8-sig", max_rows=100000):
    kind=(format_ or path.suffix[1:]).lower()
    def bounded(records):
        result=[]
        for record in records:
            if len(result)>=max_rows: raise ValueError(f"Source exceeds {max_rows:,} rows; aggregate or explicitly raise --max-rows. No sample substituted.")
            if not isinstance(record,dict) or None in record: raise ValueError("Invalid record or delimited row wider than its header")
            result.append({str(k):scalar(v) for k,v in record.items()})
        return result
    if kind in ["csv","tsv","tab"]:
        with path.open(encoding=encoding,newline="") as handle:
            reader=csv.DictReader(handle,delimiter="\t" if kind in ["tsv","tab"] else ",")
            if not reader.fieldnames or any(not name for name in reader.fieldnames) or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError("Delimited headers must be nonempty and unique")
            return bounded(reader)
    if kind in ["jsonl","ndjson"]:
        with path.open(encoding=encoding) as handle: return bounded(json.loads(line) for line in handle if line.strip())
    if kind in ["json","geojson"]:
        data=json.loads(path.read_text(encoding=encoding))
        if records_path:
            for part in records_path.split("."): data=data[part]
        if isinstance(data,dict) and data.get("type")=="FeatureCollection":
            records=[]
            for index,feature in enumerate(data["features"]):
                row=dict(feature.get("properties") or {})
                reserved={"geometry","feature_id","longitude","latitude"}
                if set(row)&reserved: raise ValueError("GeoJSON properties conflict with reserved geometry columns")
                geometry=feature.get("geometry") or {}
                row.update(feature_id=feature.get("id",index),geometry=feature.get("geometry"))
                if geometry.get("type")=="Point": row["longitude"],row["latitude"]=geometry["coordinates"][:2]
                records.append(row)
            return bounded(records)
        if not isinstance(data,list): raise ValueError("JSON must contain a record array; select nested arrays with --records-path")
        return bounded(data)
    if kind in ["sqlite","sqlite3","db"]:
        if not table: raise ValueError("SQLite requires --table")
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True) as connection:
            names={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            if table not in names: raise ValueError(f"Unknown table; available: {sorted(names)}")
            cursor=connection.execute('SELECT * FROM "'+table.replace('"','""')+'" LIMIT ?',[max_rows+1])
            keys=[column[0] for column in cursor.description]
            return bounded(dict(zip(keys,row)) for row in cursor)
    if kind=="parquet":
        import duckdb
        with duckdb.connect() as connection:
            cursor=connection.execute("SELECT * FROM read_parquet(?) LIMIT ?",[str(path),max_rows+1])
            keys=[column[0] for column in cursor.description]
            return bounded(dict(zip(keys,row)) for row in cursor.fetchall())
    if kind in ["arrow","feather","ipc"]:
        import pyarrow as pa
        import pyarrow.feather as feather
        import pyarrow.ipc as ipc
        if kind=="feather": return bounded(feather.read_table(path).to_pylist())
        with pa.memory_map(str(path),"r") as source:
            try: data=ipc.open_file(source).read_all()
            except pa.ArrowInvalid: source.seek(0);data=ipc.open_stream(source).read_all()
            return bounded(data.to_pylist())
    if kind in ["xlsx","xls"]:
        if kind=="xlsx":
            import openpyxl
            workbook=openpyxl.load_workbook(path,read_only=True,data_only=True)
            names=workbook.sheetnames
            if not sheet and len(names)!=1: raise ValueError(f"Choose --sheet from {names}")
            iterator=iter(workbook[sheet or names[0]].values)
        else:
            import xlrd
            workbook=xlrd.open_workbook(path);names=workbook.sheet_names()
            if not sheet and len(names)!=1: raise ValueError(f"Choose --sheet from {names}")
            worksheet=workbook.sheet_by_name(sheet or names[0])
            def excel_records():
                for index in range(worksheet.nrows):
                    values=[]
                    for cell in worksheet.row(index):
                        if cell.ctype==xlrd.XL_CELL_ERROR: raise ValueError("Excel error cell requires correction")
                        value=xlrd.xldate.xldate_as_datetime(cell.value,workbook.datemode) if cell.ctype==xlrd.XL_CELL_DATE else bool(cell.value) if cell.ctype==xlrd.XL_CELL_BOOLEAN else cell.value
                        values.append(value)
                    yield values
            iterator=iter(excel_records())
        headers=next(iterator,None)
        if not headers or any(value is None or str(value).strip()=="" for value in headers): raise ValueError("Excel first row must contain complete column names")
        keys=[str(value) for value in headers]
        if len(set(keys))!=len(keys): raise ValueError("Excel column names must be unique")
        return bounded(dict(zip(keys,row)) for row in iterator if any(value not in [None,""] for value in row))
    raise ValueError(f"Unsupported format: {kind}")


NUMBER=re.compile(r"^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")
DATE=re.compile(r"^\d{4}-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d))?$")


def infer_fields(rows,overrides=None):
    overrides=overrides or {};keys=list(dict.fromkeys(key for row in rows for key in row))
    if set(overrides)-set(keys): raise ValueError("Type override references an unknown field")
    fields=[];profile={}
    for key in keys:
        values=[row.get(key) for row in rows];present=[v for v in values if v is not None and v!=""]
        kind=overrides.get(key)
        if kind is None:
            if present and all(isinstance(v,bool) for v in present): kind="boolean"
            elif present and all((isinstance(v,(int,float)) and not isinstance(v,bool)) or (isinstance(v,str) and NUMBER.fullmatch(v)) for v in present): kind="number"
            elif present and all(isinstance(v,str) and DATE.fullmatch(v) for v in present):
                try:
                    for v in present: dt.datetime.fromisoformat(v.replace("Z","+00:00"))
                    kind="date"
                except ValueError: kind="string"
            else: kind="string"
        if kind not in ["number","date","string","boolean"]: raise ValueError(f"Invalid type: {kind}")
        converted=[]
        for value in values:
            if value is None or value=="": converted.append(None);continue
            if kind=="number":
                if isinstance(value,bool): raise ValueError("Boolean cannot become a number")
                number=float(value)
                if not math.isfinite(number): raise ValueError("Nonfinite numeric value")
                if number.is_integer() and abs(number)>2**53-1: raise ValueError(f"{key} exceeds exact browser integer range; use --type {key}=string")
                converted.append(int(number) if number.is_integer() else number)
            elif kind=="boolean":
                if isinstance(value,bool): converted.append(value)
                elif value in ["true","True"]: converted.append(True)
                elif value in ["false","False"]: converted.append(False)
                else: raise ValueError(f"Ambiguous boolean: {value}")
            elif kind=="date": dt.datetime.fromisoformat(str(value).replace("Z","+00:00"));converted.append(str(value))
            else: converted.append(str(value))
        for row,value in zip(rows,converted): row[key]=value
        fields.append({"key":key,"label":key.replace("_"," ").capitalize(),"type":kind})
        profile[key]={"type":kind,"nulls":sum(v is None for v in converted),"distinct":len(set(converted)-{None})}
    return fields,profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path);parser.add_argument("-o","--output",type=Path,required=True)
    for name in ["format","table","sheet","records-path","entity","label","time","x","y","color","source-url"]: parser.add_argument("--"+name)
    parser.add_argument("--encoding",default="utf-8-sig");parser.add_argument("--max-rows",type=int,default=100000)
    parser.add_argument("--type",action="append",default=[],help="FIELD=number|date|string|boolean")
    parser.add_argument("--title",default="Explore the observations");parser.add_argument("--license",default="User-supplied data; usage rights not inferred")
    parser.add_argument("--time-mode",choices=["snapshot","cumulative"],default="snapshot")
    parser.add_argument("--kind",choices=["scatter","line","bar","histogram","table"],default="scatter")
    args=parser.parse_args()
    if args.max_rows<1: parser.error("--max-rows must be positive")
    try:
        rows=read_rows(args.source,args.format,args.table,args.sheet,args.records_path,args.encoding,args.max_rows)
        if not rows: raise ValueError("No observations found")
        fields,profile=infer_fields(rows,dict(item.split("=",1) for item in args.type))
        entity=args.entity or "_record_id"
        if not args.entity:
            if entity in profile: raise ValueError("Source contains _record_id; choose --entity")
            for index,row in enumerate(rows):row[entity]=str(index)
            fields.append({"key":entity,"label":"Source row","type":"string"})
        view={"id":"main","title":args.title,"type":args.kind if args.x else "table"}
        for name in ["x","y","color"]:
            if getattr(args,name): view[name]=getattr(args,name)
        source={"title":args.source.name,"sha256":hashlib.sha256(args.source.read_bytes()).hexdigest(),"retrieved":dt.datetime.now(dt.timezone.utc).isoformat(),"license":args.license}
        if args.source_url: source["url"]=args.source_url
        document={"version":1,"id":re.sub(r"[^a-z0-9-]","-",args.source.stem.lower()),"title":args.title,"subtitle":f"{len(rows):,} observations from {args.source.name}","dataset":{"id":"imported","title":args.source.name,"entityKey":entity,"labelKey":args.label or entity,"fields":fields,"rows":rows,"sources":[source],"notes":["Verify inferred types, identifiers, dates, units, and missingness before drawing conclusions."],"transforms":["import_data.py: preserve record order; empty cells become null; nested values serialize as JSON text; explicit type overrides take precedence."]},"views":[view],"filters":[]}
        if args.time: document["time"]={"field":args.time,"mode":args.time_mode,"label":args.time}
        from build_exploration import validate
        errors=validate(document)
        if errors: raise ValueError("\n".join(errors))
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(document,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
        report={"rows":len(rows),"fields":profile,"source_sha256":source["sha256"],"missingness":"Empty cells and nonfinite source floats become null"}
        args.output.with_suffix(".profile.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2));return 0
    except (ValueError,KeyError,OSError,TypeError,sqlite3.Error) as error: print(str(error),file=sys.stderr);return 1

if __name__=="__main__":raise SystemExit(main())
