#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3", "openpyxl==3.1.5", "xlrd==2.0.2"]
# ///
"""Download primary sources, reconcile them, and author two exploration documents."""
import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request

import openpyxl
import xlrd
import yaml

FEC = {
    2006: "https://www.fec.gov/documents/1643/tables06.xls",
    2010: "https://www.fec.gov/documents/1678/tables10.xls",
    2014: "https://www.fec.gov/documents/1704/tables2014.xls",
    2018: "https://www.fec.gov/documents/2706/federalelections2018.xlsx",
    2022: "https://www.fec.gov/documents/5676/federalelections2022.xlsx",
}
METR = "https://metr.org/assets/benchmark_results_1_1.yaml"
MODEL_LABELS = {
    "claude_3_5_sonnet_20240620_inspect":"Claude 3.5 Sonnet (June 2024)",
    "claude_3_5_sonnet_20241022_inspect":"Claude 3.5 Sonnet (October 2024)",
    "claude_3_7_sonnet_inspect":"Claude 3.7 Sonnet",
    "claude_3_opus_inspect":"Claude 3 Opus",
    "claude_4_1_opus_inspect":"Claude Opus 4.1",
    "claude_4_opus_inspect":"Claude Opus 4",
    "claude_opus_4_5_inspect":"Claude Opus 4.5",
    "claude_opus_4_6_inspect":"Claude Opus 4.6",
    "claude_mythos_preview_early_inspect":"Claude Mythos Preview (early)",
    "davinci_002":"davinci-002",
    "gpt2":"GPT-2",
    "gpt_3_5_turbo_instruct":"GPT-3.5 Turbo Instruct",
    "gpt_4":"GPT-4",
    "gpt_4_1106_inspect":"GPT-4 (November 2023)",
    "gpt_4_turbo_inspect":"GPT-4 Turbo",
    "gpt_4o_inspect":"GPT-4o",
    "gpt_5_1_codex_max_inspect":"GPT-5.1 Codex Max",
    "gpt_5_2":"GPT-5.2",
    "gpt_5_2025_08_07_inspect":"GPT-5 (August 2025)",
    "gpt_5_3_codex":"GPT-5.3 Codex",
    "gpt_5_4":"GPT-5.4",
    "gemini_3_pro":"Gemini 3 Pro",
    "gemini_3_1_pro":"Gemini 3.1 Pro",
    "o1_inspect":"o1",
    "o1_preview":"o1-preview",
    "o3_inspect":"o3",
}
STATES = dict(zip(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming".split("|")))


def acquire(root, name, url, refresh):
    path = root / name
    receipt = path.with_suffix(path.suffix + ".source.json")
    if refresh or not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "DataVisualizationResearch/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
        receipt.write_text(json.dumps({"url": url, "retrieved": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2))
    metadata = json.loads(receipt.read_text()) if receipt.exists() else {"url": url, "retrieved": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()}
    metadata["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(metadata, indent=2))
    return path, metadata


def field(key, label, kind="number", unit=None, description=None):
    result = {"key": key, "label": label, "type": kind}
    if unit: result["unit"] = unit
    if description: result["description"] = description
    return result


def write_example(root, document):
    directory = root / document["id"]
    directory.mkdir(exist_ok=True)
    (directory / "exploration.json").write_text(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    rows = document["dataset"]["rows"]
    with (directory / "observations.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    return directory


def prepare_ai(root, refresh):
    path, source = acquire(root / "data", "metr_time_horizons.yaml", METR, refresh)
    data = yaml.safe_load(path.read_text())
    rows = []
    for identifier, result in data["results"].items():
        provider = "Anthropic" if identifier.startswith("claude") else "Google" if identifier.startswith("gemini") else "OpenAI"
        name = MODEL_LABELS.get(identifier,identifier)
        row = {"model": identifier, "name": name, "provider": provider, "released": result["release_date"].isoformat(), "average_score": result["metrics"]["average_score"]["estimate"], "scaffolds": "; ".join(value if value is not None else "Not specified by source" for value in result.get("scaffolds", []))}
        for threshold in [50, 80]:
            measurement = result["metrics"][f"p{threshold}_horizon_length"]
            row[f"p{threshold}_hours"] = measurement["estimate"] / 60
            row[f"p{threshold}_low"] = measurement["ci_low"] / 60
            row[f"p{threshold}_high"] = measurement["ci_high"] / 60
            assert 0 < row[f"p{threshold}_low"] <= row[f"p{threshold}_hours"] <= row[f"p{threshold}_high"], identifier
        assert row["p80_hours"] <= row["p50_hours"], identifier
        row["suite_limit"] = "Above reliable suite range" if row["p50_hours"] > 16 else "Within suite range"
        rows.append(row)
    rows.sort(key=lambda row: (row["released"], row["model"]))
    assert len({row["model"] for row in rows}) == len(rows)
    source.update(title="METR · Time Horizon 1.1 published estimates", license="Public research data; cite METR. No explicit license found in the YAML.")
    notes = [
        "Time horizon is task difficulty measured in human-expert hours, not how long an agent runs autonomously. These are fitted estimates on mostly software tasks, not a guarantee about arbitrary work.",
        "METR stopped actively updating its public page on September 8, 2026. The latest release date in this snapshot is April 7, 2026; this is not a complete ranking of current models.",
        "Vertical intervals are the source's bootstrap 95% confidence intervals. METR warns that estimates above 16 human-hours are unreliable on this task suite. Wide intervals remain visible.",
        "Playback reveals model releases in source order. It does not interpolate capability between releases. Evaluations use different agent scaffolds, listed for each model.",
    ]
    document = {"version": 1, "id": "ai-horizons", "title": "How long is a task AI can finish?", "subtitle": "26 measured models · 2019–2026 · reliability changes the answer", "category": "AI capability", "dataset": {"id": "metr-horizon-1-1", "title": "METR task-completion time horizons", "entityKey": "model", "labelKey": "name", "fields": [field("model", "Source model identifier", "string"), field("name", "Model", "string"), field("provider", "Provider", "string"), field("released", "Release date", "date"), *[field(f"p{p}_{suffix}", f"{p}% {label}", unit="human-hours") for p in [50,80] for suffix,label in [("hours","time horizon"),("low","lower 95% bound"),("high","upper 95% bound")]], field("average_score", "Average task score", unit="fraction"), field("suite_limit", "Measurement range", "string"), field("scaffolds", "Evaluation scaffolds", "string")], "rows": rows, "sources": [source, {"title": "METR methodology and limitations", "url": "https://metr.org/time-horizons/", "retrieved": source["retrieved"]}], "notes": notes, "transforms": ["scripts/prepare_examples.py: YAML source estimates and confidence bounds divided by 60 to convert minutes to hours; no estimates are recomputed. All 26 source models retained."]}, "time": {"field": "released", "mode": "cumulative", "label": "Model release date", "intervalMs": 850}, "filters": [{"field":"provider", "label":"Provider"},{"field":"suite_limit", "label":"Measurement range"}], "views": [
        {"id":"p50", "title":"At 50% success", "type":"scatter", "x":"released", "y":"p50_hours", "low":"p50_low", "high":"p50_high", "color":"provider", "xScale":"utc", "yScale":"log", "referenceY":[1,16], "referenceLabels":{"16":"16 h · suite limit"}, "description":"One point per evaluated model. Vertical bars show 95% intervals. Equal vertical distances mean equal ratios; the 16-hour reference marks the suite's reliable range.", "height":440},
        {"id":"p80", "title":"At 80% success", "type":"scatter", "x":"released", "y":"p80_hours", "low":"p80_low", "high":"p80_high", "color":"provider", "xScale":"utc", "yScale":"log", "referenceY":[1,16], "referenceLabels":{"16":"16 h · suite limit"}, "description":"Demanding a higher success rate produces a shorter time horizon. Intervals and units match the 50% view.", "height":440},
        {"id":"reliability", "title":"The reliability gap", "type":"scatter", "x":"p50_hours", "y":"p80_hours", "color":"provider", "xScale":"log", "yScale":"log", "description":"Each point compares the same model at two success thresholds; inspect a mark for both estimates.", "height":440},
        {"id":"observations", "title":"Source observations", "type":"table", "columns":["name","released","provider","p50_hours","p80_hours","suite_limit"]}
    ], "questions":[
        {"id":"release-history", "title":"Replay the measured releases", "body":"Start at the earliest source observation, then press Play. The axes stay fixed as new measurements appear.", "state":{"time":rows[0]["released"],"view":"p50","filters":{},"selected":[]}},
        {"id":"higher-reliability", "title":"What changes at 80% reliability?", "body":"Compare with the 50% view. A longer time horizon at one threshold does not imply the same result at another.", "state":{"time":rows[-1]["released"],"view":"p80","filters":{},"selected":[]}},
        {"id":"measurement-boundary", "title":"Inspect the measurement boundary", "body":"The early Mythos estimate exceeds the suite's reliable 16-hour range. Read its interval and the source caveat before interpreting the point estimate.", "state":{"time":rows[-1]["released"],"view":"p50","selected":["claude_mythos_preview_early_inspect"],"filters":{}}}
    ], "links":[{"label":"Explore five U.S. midterms", "href":"../midterm-votes/index.html"}]}
    write_example(root, document)
    return {"rows":len(rows),"release_range":[rows[0]["released"],rows[-1]["released"]],"checks":["all source models retained","unique model identities","all estimates within source intervals","80% horizons never exceed 50% horizons"]}


def workbook_rows(path):
    if path.suffix == ".xls":
        workbook = xlrd.open_workbook(path)
        return {sheet.name:[sheet.row_values(i) for i in range(sheet.nrows)] for sheet in workbook.sheets()}
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return {sheet.title:list(sheet.values) for sheet in workbook}


def prepare_elections(root, refresh):
    rows, sources, verification = [], [], []
    for year, url in FEC.items():
        path, source = acquire(root / "data", f"fec_{year}.{url.rsplit('.',1)[1]}", url, refresh)
        sheets = workbook_rows(path)
        party_rows = next(value for key,value in sheets.items() if "Table 5" in key)
        total_rows = next(value for key,value in sheets.items() if "Table 1." in key or "Table 1 " in key)
        index = 1 if year == 2010 else 0
        offset = 5 if year == 2010 else 4
        totals = {}
        for values in total_rows:
            # 2010 Table 1 also has a full state-name column.
            if values[index] in STATES:
                totals[values[index]] = int(values[index+2])
        full_totals = [0,0,0]
        declared_totals = None
        year_rows = []
        for values in party_rows:
            state = str(values[index]).strip()
            if state.upper().startswith("TOTAL"):
                declared_totals = [int(value or 0) for value in values[offset:offset+3]]
                continue
            if len(state) != 2 or not state.isupper(): continue
            counts = [int(value or 0) for value in values[offset:offset+3]]
            full_totals = [a+b for a,b in zip(full_totals, counts)]
            if state not in STATES: continue
            democratic, republican, other = counts
            total = sum(counts)
            assert total > 0 and all(value >= 0 for value in counts)
            assert total == totals[state], (year,state,total,totals.get(state))
            row = {"state":state, "name":STATES[state], "year":year, "democratic_votes":democratic, "republican_votes":republican, "other_votes":other, "total_votes":total, "democratic_share":100*democratic/total, "republican_share":100*republican/total, "margin":100*(democratic-republican)/total, "leader":"Democratic" if democratic>republican else "Republican" if republican>democratic else "Tie", "source_blank_parties":", ".join(party for party,value in zip(["Democratic","Republican","Other"],values[offset:offset+3]) if value in [None, ""])}
            year_rows.append(row)
        assert len(year_rows) == 50 and len({row['state'] for row in year_rows}) == 50, year
        assert full_totals == declared_totals, (year,full_totals,declared_totals)
        rows.extend(sorted(year_rows,key=lambda row:row["state"]))
        source.update(title=f"FEC Federal Elections {year} · Table 5", license="U.S. federal government election compilation; source attribution retained.")
        sources.append(source)
        verification.append({"year":year,"states":50,"party_totals_all_jurisdictions":full_totals,"published_totals":declared_totals,"fifty_state_votes":sum(row["total_votes"] for row in year_rows),"checks":["50 states exactly once","all 50 state party sums match separate Table 1 House totals","all jurisdictions reconcile to published Table 5 party totals"]})
    notes = [
        "Historical House vote compilations for five midterm years, 2006–2022. These are not polling data, a forecast, or results for the 2026 election.",
        "Only the 50 states are plotted; D.C. and territories are excluded. Share denominators include Democratic, Republican and Other votes. The margin is Democratic share minus Republican share, in percentage points.",
        "FEC tables can include both full-term and unexpired-term contests, and Louisiana December elections where noted. Counts are recorded House candidate votes, not unique voters or a turnout rate. They should not be interpreted as seat shares.",
        "Unopposed races, different ballot rules and redistricting affect comparisons. A state's House vote share is not a standardized measure of statewide political preference.",
        "Source blanks for a party mean no recorded votes in the compilation. They contribute zero to the published sums; the original blank categories are retained in Source blank parties. No missing observations are interpolated.",
    ]
    fields = [field("state","State code","string"),field("name","State","string"),field("year","Election year"),*[field(key,label,unit="candidate votes") for key,label in [("democratic_votes","Democratic votes"),("republican_votes","Republican votes"),("other_votes","Other votes"),("total_votes","Total recorded House votes")]], field("democratic_share","Democratic share",unit="percent"),field("republican_share","Republican share",unit="percent"),field("margin","Democratic minus Republican share",unit="percentage points"),field("leader","Party with more recorded votes","string"),field("source_blank_parties","Source blank parties","string")]
    categories={"colorDomain":["Democratic","Republican","Tie"]}
    document={"version":1,"id":"midterm-votes","title":"Five midterms. Fifty states.","subtitle":"How recorded U.S. House votes shifted from 2006 to 2022", "category":"Election history","dataset":{"id":"fec-house-state-votes","title":"Official FEC House votes by state and party","entityKey":"state","labelKey":"name","fields":fields,"rows":rows,"sources":sources,"notes":notes,"transforms":["scripts/prepare_examples.py: read general-election D/R/Other columns from Table 5, retain 50 states, calculate shares and D–R percentage-point margins. Reconcile each state with independent Table 1 totals, and all jurisdictions with published Table 5 party totals."]},"time":{"field":"year","mode":"snapshot","label":"Midterm election","intervalMs":1300},"filters":[{"field":"name","label":"State"},{"field":"leader","label":"Recorded vote leader"}],"views":[
        {"id":"landscape","title":"The state landscape","type":"scatter","x":"total_votes","y":"margin","color":"leader","yDomain":[-100,100],"referenceY":[0],"description":"One point per state. Above zero: more Democratic votes. Below: more Republican votes. Horizontal position counts recorded House candidate votes; it is not turnout.","height":440,**categories},
        {"id":"margins","title":"Compare state margins","type":"bar","x":"state","y":"margin","aggregate":"mean","color":"leader","description":"D–R margin in percentage points. The zero baseline and full-range scale stay fixed across elections.","yDomain":[-100,100],"height":440,**categories},
        {"id":"history","title":"Follow states through time","type":"line","x":"year","y":"margin","series":"state","color":"state","timeMode":"all","yDomain":[-100,100],"referenceY":[0],"description":"Observed election-year endpoints connected for comparison. Filter states to isolate a cohort; lines do not imply observations between elections.","height":440},
        {"id":"observations","title":"Source observations","type":"table","columns":["name","year","democratic_votes","republican_votes","other_votes","margin"]}
    ],"questions":[
        {"id":"replay","title":"Replay five elections","body":"Start in 2006, then press Play. Each frame is a real election year; the axes and zero reference stay fixed.","state":{"time":2006,"view":"landscape","filters":{},"selected":[]}},
        {"id":"three-states","title":"Compare Michigan, Pennsylvania and Wisconsin","body":"Follow three states across five midterms. These are aggregate House votes, affected by district boundaries and uncontested races; they are not presidential vote shares.","state":{"time":2022,"view":"history","filters":{"name":["Michigan","Pennsylvania","Wisconsin"]},"selected":[]}},
        {"id":"latest","title":"Inspect the 2022 compilation","body":"Select a state to inspect exact party totals and their denominator. Source files and reconciliation results accompany the page.","state":{"time":2022,"view":"landscape","filters":{},"selected":[]}}
    ],"links":[{"label":"Explore AI time horizons","href":"../ai-horizons/index.html"}]}
    write_example(root,document)
    return {"rows":len(rows),"years":list(FEC),"reconciliation":verification}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True); (args.output/"data").mkdir(exist_ok=True)
    report={"ai":prepare_ai(args.output,args.refresh),"midterms":prepare_elections(args.output,args.refresh)}
    (args.output/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__ == "__main__": main()
