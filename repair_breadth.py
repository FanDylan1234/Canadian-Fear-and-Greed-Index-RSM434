"""Replace Venture breadth with a validated, paired TSX Composite history."""
import datetime as dt
import json
from pathlib import Path
import pandas as pd
from fgindex.data import ROOT
from fgindex.pipeline import atomic_text
from pull_bloomberg import BloombergClient
from data_checks import yesterday, check_history

# These candidates are evidenced in the project's saved Bloomberg field/security search.
PAIRS = [
    (("SPTSX Index", "INDX_ADV_NUM"), ("SPTSX Index", "INDX_DECL_NUM")),
    (("STSXADV Index", "PX_LAST"), ("STSXDCL Index", "PX_LAST")),
    (("TSXADV Index", "PX_LAST"), ("TSXDCL Index", "PX_LAST")),
]


def repair(raw_dir=None, client_factory=BloombergClient, start="2008-01-01"):
    raw_dir = Path(raw_dir or ROOT / "data-access-results/raw")
    end = yesterday()
    client = client_factory()
    attempts, candidates = [], []
    try:
        for pair in PAIRS:
            chosen = []
            try:
                for name, (security, field) in zip(("tsx_advancing", "tsx_declining"), pair):
                    print(f"Checking Composite breadth: {security} / {field}", flush=True)
                    meta = client.metadata(security, field)
                    names = [r.get("fieldData", {}).get("NAME", "") for msg in meta.get("security_details", []) for r in msg.get("securityData", [])]
                    if not names or any("venture" in n.lower() for n in names) or not any("composite" in n.lower() for n in names):
                        raise ValueError("Security metadata does not confirm TSX Composite")
                    rows = client.history(security, field, start, end)
                    coverage = check_history(rows, {"kind": "count"}, start, end)
                    if "COUNTS_NOT_NONNEGATIVE_INTEGERS" in coverage["issues"] or coverage["duplicate_dates"]:
                        raise ValueError("Invalid count history")
                    chosen.append(dict(id=name, security=security, field=field, rows=rows, metadata=meta,
                                       coverage=coverage, definition_verified=True, status="PASS" if coverage["status"]=="RANGE_OK" else "REVIEW"))
                common_start = max(x["coverage"]["first_date"] for x in chosen)
                common_end = min(x["coverage"]["last_date"] for x in chosen)
                if (dt.date.fromisoformat(end)-dt.date.fromisoformat(common_end)).days > 7:
                    raise ValueError("Paired history is stale")
                candidates.append((common_start, chosen))
                attempts.append(dict(pair=pair, first=common_start, last=common_end, status="Eligible"))
                if common_start <= start:
                    break
            except Exception as exc:
                attempts.append(dict(pair=pair, error=str(exc)))
    finally:
        client.close()
    atomic_text(raw_dir.parent / "breadth-repair-report.json", json.dumps(attempts, indent=2))
    if not candidates:
        raise RuntimeError("No valid TSX Composite pair downloaded. Venture data remains excluded. See breadth-repair-report.json.")
    _, chosen = min(candidates, key=lambda x: x[0])
    report_path = raw_dir.parent / "bloomberg-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig")) if report_path.exists() else {"results": []}
    previous = {r["id"]: r for r in report["results"]}
    for item in chosen:
        rows = item.pop("rows")
        target = raw_dir / (item["id"]+".csv")
        if target.exists():
            archive = raw_dir.parent / "before-composite-repair" / target.name
            if not archive.exists():
                atomic_text(archive, target.read_text(encoding="utf-8-sig"))
        atomic_text(target, pd.DataFrame(rows).to_csv(index=False))
        previous[item["id"]] = item
        print(f"Selected {item['security']} / {item['field']}: {item['coverage']['first_date']} to {item['coverage']['last_date']}", flush=True)
    report["results"] = list(previous.values())
    atomic_text(report_path, json.dumps(report, indent=2, default=str))
    return chosen


if __name__ == "__main__":
    repair()
