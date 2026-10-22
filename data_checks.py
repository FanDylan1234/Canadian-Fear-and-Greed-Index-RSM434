"""Shared history and data-quality checks; no scoring or returns."""
import datetime as dt
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent

def yesterday():
    # Completed calendar date in Toronto; intraday current-day data is excluded.
    from zoneinfo import ZoneInfo
    return (dt.datetime.now(ZoneInfo("America/Toronto")).date()-dt.timedelta(days=1)).isoformat()

def check_history(rows, spec, start, end):
    wanted_start = max(start, spec.get("expected_start", start))
    wanted_end = min(end, spec.get("expected_end", end))
    valid = [r for r in rows if r.get("value") is not None and wanted_start <= r["date"][:10] <= wanted_end]
    dates = sorted(set(r["date"][:10] for r in valid))
    issues = []
    if not dates:
        return {"status":"NO_REQUIRED_HISTORY", "expected_start":wanted_start, "expected_end":wanted_end,
                "numeric_rows":0, "issues":["No numeric data in required period."]}
    if dates[0] > (dt.date.fromisoformat(wanted_start)+dt.timedelta(days=10)).isoformat():
        issues.append("STARTS_LATE")
    if dates[-1] < (dt.date.fromisoformat(wanted_end)-dt.timedelta(days=10)).isoformat():
        issues.append("ENDS_EARLY")
    gaps = [{"after":a, "before":b, "calendar_days":(dt.date.fromisoformat(b)-dt.date.fromisoformat(a)).days}
            for a,b in zip(dates, dates[1:]) if (dt.date.fromisoformat(b)-dt.date.fromisoformat(a)).days>10]
    if gaps:
        issues.append("LONG_INTERNAL_GAPS")
    duplicates = len(valid)-len(dates)
    if duplicates:
        issues.append("DUPLICATE_DATES")
    values = [r["value"] for r in valid]
    kind = spec.get("kind")
    if kind == "count" and any(v < 0 or abs(v-round(v)) > 1e-6 for v in values):
        issues.append("COUNTS_NOT_NONNEGATIVE_INTEGERS")
    if kind in ("level","volatility") and any(v <= 0 for v in values):
        issues.append("NONPOSITIVE_LEVEL")
    longest, repeat = 1, 1
    ordered = sorted(valid, key=lambda r:r["date"])
    for a,b in zip(ordered,ordered[1:]):
        repeat = repeat+1 if a["value"] == b["value"] else 1
        longest = max(longest,repeat)
    if longest >= 10:
        issues.append("REPEATED_VALUE_10_PLUS_ROWS")
    weekdays = 0
    date_set = set(dates)
    cursor = dt.date.fromisoformat(wanted_start)
    while cursor.isoformat() <= wanted_end:
        if cursor.weekday()<5 and cursor.isoformat() not in date_set:
            weekdays += 1
        cursor += dt.timedelta(days=1)
    return dict(status="COVERAGE_REVIEW" if issues else "RANGE_OK",
                expected_start=wanted_start, expected_end=wanted_end,
                first_date=dates[0], last_date=dates[-1], numeric_rows=len(valid),
                missing_values=sum(r.get("value") is None for r in rows if wanted_start <= r["date"][:10] <= wanted_end),
                duplicate_dates=duplicates, long_gaps=gaps, issues=issues,
                weekdays_without_observation=weekdays,
                calendar_note="Weekday gaps include exchange holidays; RANGE_OK is only a range/basic-quality screen, not certified daily completeness.",
                longest_identical_value_run=longest)

def show_result(result):
    print(f"  [{result['status']}] {result['id']}", flush=True)
    if result.get("reason"):
        print("  "+result["reason"], flush=True)
    if result.get("coverage"):
        c=result["coverage"]
        print(f"  Required: {c['expected_start']} -> {c['expected_end']}", flush=True)
        print(f"  Coverage: {c['status']} | rows={c['numeric_rows']:,} | {c.get('first_date','none')} -> {c.get('last_date','none')}", flush=True)
        print("  Issues: "+(", ".join(c.get("issues",[])) or "none in basic screen"), flush=True)
        print(f"  Missing weekdays (includes holidays): {c.get('weekdays_without_observation','n/a')}", flush=True)
    for row in result.get("sample",[]):
        print(f"    {row['date']}: {row['value']}", flush=True)

def save_report(output, filename, report):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    target=output/filename
    target.write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
    counts=Counter(r["status"] for r in report["results"])
    print("\nSUMMARY: "+" | ".join(f"{key}={value}" for key,value in counts.items()),flush=True)
    print("Report: "+str(target.resolve()),flush=True)
