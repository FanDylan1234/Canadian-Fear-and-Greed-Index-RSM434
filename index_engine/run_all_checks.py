"""Check source access and write a coverage report."""
import datetime as dt
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
from index_engine.data_checks import yesterday, save_report

def main(start="2010-01-01",end=None):
    end=end or yesterday()
    dt.date.fromisoformat(start)
    dt.date.fromisoformat(end)
    if start>end:
        raise ValueError("Start date must precede end date")
    print("\nALL PROJECT DATA CHECKS: "+start+" -> "+end,flush=True)
    from index_engine.pull_data import main as public_checks
    from index_engine.pull_bloomberg import run_checks
    output=ROOT/"data-access-results"
    public=public_checks(output,start,end)
    bloomberg=run_checks(start,end,output=output)
    report=dict(tested_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                start=start,end=end,results=public["results"]+bloomberg["results"],
                requirements_source="Project 2 p.2; Overview p.2")
    required=[r for r in report["results"] if r["id"]!="mx_vixi_snapshot"]
    report["all_required_checks_passed"]=len(required)==13 and all(r["status"]=="PASS" for r in required)
    report["project_gaps"]=[
        "Put/call source starts 2011, leaving 2010 unresolved for any design using it.",
        "Canadian volatility transition 2020-21 requires an explicit fallback decision; series remain separate.",
        "Range/quality checks use calendar heuristics, not authoritative exchange calendars.",
        "Candidate mappings need definition/universe/units review before being marked verified.",
        "No fallback is spliced into a Canadian dataset. No indicator/index construction is performed."
    ]
    save_report(output,"all-checks-report.json",report)
    lines=["# All source checks","",f"Requested: {start} to {end}","",
           "| Dataset | Status | First | Last |","|---|---|---|---|"]
    for result in report["results"]:
        c=result.get("coverage",{})
        lines.append("| "+" | ".join(str(v) for v in (result["id"],result["status"],c.get("first_date",result.get("first_date","")),c.get("last_date",result.get("last_date",""))))+" |")
    lines+=["","## Known project gaps",""]+["- "+s for s in report["project_gaps"]]
    (output/"all-checks-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\nAll required checks passed: "+str(report["all_required_checks_passed"]),flush=True)
    print("Send all-checks-report.json and bloomberg-report.json for definition review.",flush=True)
    return report

if __name__=="__main__":
    report=main()
    if "IPython" not in sys.modules and not report["all_required_checks_passed"]:
        raise SystemExit(1)
