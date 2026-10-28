"""Executable cross-format equivalence and data-integrity checks."""
import copy
import csv
import datetime as dt
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from import_data import read_rows, infer_fields, scalar
from build_exploration import build, validate


class ImportIntegrity(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.rows=[{"id":"001","time":2020,"value":1.25},{"id":"002","time":2024,"value":None}]
    def tearDown(self):self.temporary.cleanup()

    def assert_rows(self,path,**kwargs):
        rows=read_rows(path,**kwargs);fields,_=infer_fields(rows)
        self.assertEqual(rows,self.rows)
        self.assertEqual({f["key"]:f["type"] for f in fields},{"id":"string","time":"number","value":"number"})

    def test_text_formats(self):
        for extension,delimiter in [("csv",","),("tsv","\t")]:
            path=self.root/f"observations.{extension}"
            with path.open("w",newline="") as handle:
                writer=csv.DictWriter(handle,self.rows[0],delimiter=delimiter);writer.writeheader();writer.writerows(self.rows)
            self.assert_rows(path)
        path=self.root/"observations.json";path.write_text(json.dumps(self.rows));self.assert_rows(path)
        path=self.root/"observations.jsonl";path.write_text("\n".join(json.dumps(r) for r in self.rows));self.assert_rows(path)
        path=self.root/"nested.json";path.write_text(json.dumps({"data":{"records":self.rows}}));self.assert_rows(path,records_path="data.records")

    def test_sqlite_is_read_only(self):
        path=self.root/"observations.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE observations (id TEXT,time INTEGER,value REAL)")
            connection.executemany("INSERT INTO observations VALUES (:id,:time,:value)",self.rows)
        before=path.read_bytes();self.assert_rows(path,table="observations");self.assertEqual(before,path.read_bytes())
        with self.assertRaises(ValueError):read_rows(path,table='observations"; DROP TABLE observations; --')

    def test_columnar_formats(self):
        import pyarrow as pa
        import pyarrow.parquet as parquet
        import pyarrow.feather as feather
        import pyarrow.ipc as ipc
        data=pa.Table.from_pylist(self.rows)
        path=self.root/"observations.parquet";parquet.write_table(data,path);self.assert_rows(path)
        path=self.root/"observations.feather";feather.write_feather(data,path);self.assert_rows(path)
        for mode in ["file","stream"]:
            path=self.root/f"{mode}.arrow"
            with pa.OSFile(str(path),"wb") as output:
                with (ipc.new_file if mode=="file" else ipc.new_stream)(output,data.schema) as writer:writer.write_table(data)
            self.assert_rows(path)

    def test_excel(self):
        import openpyxl
        path=self.root/"observations.xlsx";workbook=openpyxl.Workbook();sheet=workbook.active
        sheet.append(list(self.rows[0]))
        for row in self.rows:sheet.append(list(row.values()))
        workbook.save(path);self.assert_rows(path)
        workbook.create_sheet("Second");workbook.save(path)
        with self.assertRaises(ValueError):read_rows(path)
        self.assert_rows(path,sheet=sheet.title)

    def test_legacy_excel(self):
        import xlwt
        path=self.root/"observations.xls";workbook=xlwt.Workbook();sheet=workbook.add_sheet("Observations")
        for column,key in enumerate(self.rows[0]):sheet.write(0,column,key)
        for index,row in enumerate(self.rows,1):
            for column,value in enumerate(row.values()):
                if value is not None:sheet.write(index,column,value)
        workbook.save(str(path));self.assert_rows(path)

    def test_geojson_geometry_preserved(self):
        path=self.root/"points.geojson";geometry={"type":"Point","coordinates":[-87.6,41.8]}
        path.write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","id":"a","properties":{"value":3},"geometry":geometry}]}))
        row=read_rows(path)[0];self.assertEqual(row["longitude"],-87.6);self.assertEqual(json.loads(row["geometry"]),geometry)

    def test_reject_truncation_and_precision_loss(self):
        path=self.root/"observations.json";path.write_text(json.dumps(self.rows))
        with self.assertRaises(ValueError):read_rows(path,max_rows=1)
        with self.assertRaises(ValueError):infer_fields([{"id":"9007199254740993"}])
        rows=[{"id":"9007199254740993"}];infer_fields(rows,{"id":"string"});self.assertEqual(rows[0]["id"],"9007199254740993")
        rows=[{"value":True},{"value":False}];fields,_=infer_fields(rows);self.assertEqual(fields[0]["type"],"boolean")

    def test_calendar_dates_and_timezone_semantics(self):
        self.assertEqual(scalar(dt.datetime(2026,10,28)),"2026-10-28")
        for value,kind in [("2026-10-28","date"),("2026-10-28T13:00:00Z","date"),("2026-10-28T13:00:00","string"),("10/28/2026","string"),("2026-02-30","string")]:
            fields,_=infer_fields([{"when":value}]);self.assertEqual(fields[0]["type"],kind)

    def test_bad_csv_headers_and_rows(self):
        path=self.root/"observations.csv";path.write_text("id,id\na,b\n")
        with self.assertRaises(ValueError):read_rows(path)
        path.write_text("id,value\na,1,extra\n")
        with self.assertRaises(ValueError):read_rows(path)

    def test_local_file_cli(self):
        source=self.root/"observations.json";source.write_text(json.dumps(self.rows))
        output=self.root/"exploration.json"
        command=[sys.executable,str(Path(__file__).resolve().parents[2]/"scripts/import_data.py"),str(source),"--entity","id","--x","time","--y","value","-o",str(output)]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        document=json.loads(output.read_text());self.assertEqual(document["dataset"]["rows"],self.rows)
        self.assertEqual(len(document["dataset"]["sources"][0]["sha256"]),64)
        self.assertNotIn("url",document["dataset"]["sources"][0])


class CompilationIntegrity(unittest.TestCase):
    def fixture(self):
        return {"version":1,"id":"example","title":"Example","dataset":{"id":"data","entityKey":"id","labelKey":"id","fields":[{"key":"id","type":"string"},{"key":"time","type":"number"},{"key":"value","type":"number"}],"rows":[{"id":"a","time":2020,"value":2}],"sources":[]},"time":{"field":"time","mode":"snapshot"},"views":[{"id":"main","type":"scatter","x":"time","y":"value"}]}
    def test_identity_and_field_integrity(self):
        document=self.fixture();self.assertEqual(validate(document),[])
        document["dataset"]["rows"].append(copy.deepcopy(document["dataset"]["rows"][0]));self.assertTrue(any("Duplicate" in e for e in validate(document)))
        document=self.fixture();document["views"][0]["y"]="unknown";self.assertTrue(validate(document))
        document=self.fixture();document["dataset"]["rows"][0]["value"]=float("inf");self.assertTrue(validate(document))
    def test_executable_metadata_rejected_or_escaped(self):
        document=self.fixture();document["dataset"]["sources"]=[{"url":"javascript:alert(1)"}];self.assertTrue(validate(document))
        document=self.fixture();document["title"]='</script><script>alert("injected")</script>'
        assets=Path(__file__).resolve().parents[2]/"assets"
        if not (assets/"runtime.js").exists():self.skipTest("Renderer not yet installed")
        page=build(document);self.assertNotIn('<script>alert("injected")</script>',page)
        self.assertIn('\\u003c/script>',page)


if __name__=="__main__":unittest.main()
