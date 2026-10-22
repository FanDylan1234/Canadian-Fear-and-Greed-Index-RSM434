"""Optional Bloomberg historical-data probe. Run on an entitled lab terminal.
Python 3.10+ and Bloomberg's official blpapi package are required.
No index construction, scoring, or backtesting.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent

def pull(session, blpapi, spec, start, end):
    request = session.getService("//blp/refdata").createRequest("HistoricalDataRequest")
    request.getElement("securities").appendValue(spec["security"])
    request.getElement("fields").appendValue(spec["field"])
    request.set("startDate", start.replace("-", ""))
    request.set("endDate", end.replace("-", ""))
    request.set("periodicitySelection", "DAILY")
    # Do not invent observations on non-trading days or fill missing values.
    correlation = session.sendRequest(request)
    rows, errors = [], []
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            event = session.nextEvent(1000)
            for message in event:
                if correlation not in message.correlationIds():
                    continue
                if message.hasElement("responseError"):
                    errors.append(str(message.getElement("responseError")))
                if message.hasElement("securityData"):
                    data = message.getElement("securityData")
                    if data.hasElement("securityError"):
                        errors.append(str(data.getElement("securityError")))
                    if data.hasElement("fieldExceptions"):
                        exceptions = data.getElement("fieldExceptions")
                        if exceptions.numValues():
                            errors.append(str(exceptions))
                    if data.hasElement("fieldData"):
                        values = data.getElement("fieldData")
                        for i in range(values.numValues()):
                            row = values.getValueAsElement(i)
                            if row.hasElement(spec["field"]) and not row.getElement(spec["field"]).isNull():
                                value = row.getElementAsFloat(spec["field"])
                                if math.isfinite(value):
                                    rows.append({"date": str(row.getElementAsDatetime("date")), "value": value})
                if message.messageType() == blpapi.Name("RequestFailure"):
                    errors.append(str(message))
            if event.eventType() == blpapi.Event.RESPONSE:
                if errors:
                    raise RuntimeError("; ".join(errors))
                if not rows:
                    raise RuntimeError("No numeric historical observations returned")
                return rows
            if errors:
                raise RuntimeError("; ".join(errors))
        raise TimeoutError("Bloomberg request exceeded 45 seconds")
    finally:
        session.cancel(correlation)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "bloomberg-series.json")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default=dt.date.today().isoformat())
    args = parser.parse_args()
    dt.date.fromisoformat(args.start)
    dt.date.fromisoformat(args.end)
    if args.start > args.end:
        parser.error("--start must precede --end")
    specs = json.loads(args.config.read_text(encoding="utf-8"))
    output = ROOT / "data-access-results"
    (output / "raw").mkdir(parents=True, exist_ok=True)
    report = {"tested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "results": []}
    session = None
    blocker = None
    try:
        import blpapi
        options = blpapi.SessionOptions()
        options.setServerHost("localhost")
        options.setServerPort(8194)
        options.setConnectTimeout(5000)
        session = blpapi.Session(options)
        if not session.start():
            raise RuntimeError("Desktop API session did not start")
        if not session.openService("//blp/refdata"):
            raise RuntimeError("Cannot open Bloomberg reference-data service")
    except Exception as exc:
        blocker = str(exc)
    try:
        for spec in specs:
            result = {"id": spec["id"], "security": spec.get("security"), "field": spec.get("field")}
            if not spec.get("security") or not spec.get("field"):
                result.update(status="NOT_CONFIGURED", reason="Confirm security and historical field in Bloomberg, then fill configuration.")
                if blocker:
                    result["session_blocker"] = blocker
            elif blocker:
                result.update(status="BLOCKED", reason=blocker)
            else:
                try:
                    rows = pull(session, blpapi, spec, args.start, args.end)
                    safe_id = spec["id"]
                    if not safe_id.replace("_", "").isalnum():
                        raise ValueError("Dataset id may contain only letters, digits and underscores")
                    with (output / "raw" / (safe_id + ".csv")).open("w", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=["date", "value"])
                        writer.writeheader()
                        writer.writerows(rows)
                    dates = sorted(r["date"] for r in rows)
                    result.update(status="PASS", numeric_rows=len(rows), first_date=dates[0], last_date=dates[-1])
                except Exception as exc:
                    result.update(status="FAIL", reason=str(exc))
            report["results"].append(result)
    finally:
        if session is not None:
            session.stop()
    (output / "bloomberg-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(r["status"] == "PASS" for r in report["results"]) else 1

if __name__ == "__main__":
    raise SystemExit(main())
