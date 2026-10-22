"""Public data access checks. Open this file in Spyder and press F5.
Python 3.10+; standard library only. No index calculations.
"""
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
import urllib.request
from collections import Counter

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data-access-results"
BOC = "BD.CDN.10YR.DQ.YLD"
SOURCES = [
    ("fred_vix", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&cosd=2010-01-01", "csv",
     "US VIX, not Canadian volatility."),
    ("boc_canada_10y", "https://www.bankofcanada.ca/valet/observations/" + BOC + "/json?start_date=2010-01-01", "json",
     "Yield levels are not bond total returns."),
    ("mx_equity_put_call", "https://www.m-x.ca/files/ratio-equity.csv", "csv",
     "Starts in 2011, not 2010. Check latest date for publication delays."),
    ("mx_vixi_snapshot", "https://www.m-x.ca/files/json/vixi.json", "json",
     "Current intraday snapshot only; historical daily access remains unverified."),
]

def numeric(value):
    if value is None or str(value).strip() in ("", "."):
        return None
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Non-finite numeric observation")
    return value

def parse(source, text):
    if source in ("fred_vix", "mx_equity_put_call"):
        delimiter = "," if source == "fred_vix" else ";"
        date_key, value_key = ("observation_date", "VIXCLS") if source == "fred_vix" else ("Date", "Ratio")
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff").rstrip("\x00 \t\r\n")), delimiter=delimiter)
        required = {date_key, value_key}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Unexpected CSV schema (possibly an HTML error page)")
        return [(r[date_key], numeric(r[value_key])) for r in reader]
    data = json.loads(text)
    if source == "boc_canada_10y":
        if BOC not in data.get("seriesDetail", {}) or not isinstance(data.get("observations"), list):
            raise ValueError("Unexpected Bank of Canada schema")
        return [(r["d"], numeric(r.get(BOC, {}).get("v"))) for r in data["observations"]]
    if not isinstance(data, list):
        raise ValueError("Unexpected VIXI schema")
    return [(dt.datetime.fromtimestamp(r[0] / 1000, dt.timezone.utc).isoformat(), numeric(r[1])) for r in data]

def summarize(rows):
    if not rows:
        raise ValueError("Empty response")
    for date, _ in rows:
        dt.datetime.fromisoformat(date)
    valid = sorted((date, value) for date, value in rows if value is not None)
    if not valid:
        raise ValueError("No numeric observations")
    dates = [r[0] for r in rows]
    return dict(rows=len(rows), numeric_rows=len(valid), missing_rows=len(rows)-len(valid),
                duplicate_dates=len(dates)-len(set(dates)), first_date=valid[0][0], last_date=valid[-1][0],
                calendar_days_since_last=(dt.datetime.now(dt.timezone.utc).date()-dt.date.fromisoformat(valid[-1][0][:10])).days)

def main(output=OUTPUT):
    output = Path(output)
    (output / "raw").mkdir(parents=True, exist_ok=True)
    report = dict(tested_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  requested_start="2010-01-01", results=[])
    print("\nCANADIAN FEAR AND GREED INDEX - PUBLIC DATA CHECKS", flush=True)
    print("PASS = retrieved numeric data; PARTIAL = limited coverage; FAIL = retrieval/parsing error.", flush=True)
    for index, (source, url, ext, note) in enumerate(SOURCES, 1):
        print(f"\n[{index}/{len(SOURCES)}] Testing {source} ...", flush=True)
        result = dict(id=source, url=url, note=note)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "RSM434-data-access-check/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8-sig")
                result["http_status"] = response.status
            rows = parse(source, text)
            result.update(summarize(rows))
            result["status"] = "PARTIAL" if source == "mx_vixi_snapshot" else "PASS"
            (output / "raw" / (source + "." + ext)).write_text(text, encoding="utf-8")
            print(f"  [{result['status']}] {result['numeric_rows']:,} numeric observations", flush=True)
            print(f"  Dates: {result['first_date']} -> {result['last_date']}", flush=True)
            print(f"  Missing: {result['missing_rows']} | Duplicates: {result['duplicate_dates']} | Age: {result['calendar_days_since_last']} calendar days", flush=True)
            print("  Latest 3 numeric observations:", flush=True)
            for date, value in sorted(r for r in rows if r[1] is not None)[-3:]:
                print(f"    {date}: {value}", flush=True)
        except Exception as exc:
            result.update(status="FAIL", error=str(exc))
            print(f"  [FAIL] {exc}", flush=True)
        print("  Note: " + note, flush=True)
        report["results"].append(result)
    print("\n[NOT_TESTED] Bloomberg: run pull_bloomberg.py on the signed-in lab terminal.", flush=True)
    report["bloomberg_status"] = "NOT_TESTED"
    (output / "python-report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    counts = Counter(r["status"] for r in report["results"])
    print("\nSUMMARY: " + " | ".join(f"{key}={counts[key]}" for key in ("PASS", "PARTIAL", "FAIL")), flush=True)
    print("Saved report: " + str((output / "python-report.json").resolve()), flush=True)
    return report

if __name__ == "__main__":
    report = main()
    # Keep Spyder's console interactive; still return a failing exit code in a shell.
    import sys
    if "IPython" not in sys.modules and any(r["status"] == "FAIL" for r in report["results"]):
        raise SystemExit(1)
