"""Bloomberg access, definition discovery and history checks.
Run on the signed-in lab terminal. Spyder: open this file and press F5.
Uses per-request event queues, bounded candidate search and daily historical pulls.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
import re
import sys
import time
from fgindex.data_checks import ROOT, yesterday, check_history, show_result, save_report


def normalize_security(security):
    """Security lookup uses yellow-key tags; historical requests need parsekeys."""
    security=security.strip().removeprefix("/ticker/")
    security=re.sub(r"\s*<index>\s*$"," Index",security,flags=re.I)
    return security

def eligible_field(spec, item):
    text=(item.get("field","")+" "+item.get("description","")+" "+item.get("documentation","")).lower()
    if not all(term.lower() in text for term in spec.get("field_terms",[])):
        return False
    if spec.get("kind")!="count":
        return True
    if re.search(r"percent|percentage|ratio|pct|volume|average|payment|grant|collection|account|covid|minus|net|cumulative",text):
        return False
    # A mere occurrence of "advance" is not evidence of market breadth.
    return bool(re.search(r"\b(issues?|members?|stocks?|securities)\b",text.replace("_"," ")))

def eligible_instrument(spec,item):
    text=normalize_security(item.get("security",""))+" "+item.get("description","")
    if re.search(r"Venture",text,re.I):
        return False
    if not re.search(r"TSX|Toronto",text,re.I):
        return False
    if not re.search(spec.get("instrument_pattern","."),text):
        return False
    if spec.get("kind")=="count" and re.search(
            r"volume|\bvol\b|VOLD|VOLU|ratio|percent|cumulative|advance.?decline|advances?.?(and|/)?.?declines?|\bnet\b|\bline\b",text,re.I):
        return False
    return True


class BloombergClient:
    def __init__(self):
        import blpapi
        self.api = blpapi
        options = blpapi.SessionOptions()
        options.setServerHost("localhost")
        options.setServerPort(8194)
        options.setConnectTimeout(5000)
        self.session = blpapi.Session(options)
        self.services = set()
        self.cache = {}
        if not self.session.start():
            self.close()
            raise RuntimeError("Bloomberg Desktop API did not start. Sign in to the lab terminal.")
        try:
            self.service("//blp/refdata")
        except Exception:
            self.close()
            raise

    def close(self):
        self.session.stop()

    def service(self, name):
        if name not in self.services:
            if not self.session.openService(name):
                raise RuntimeError("Cannot open "+name)
            self.services.add(name)
        return self.session.getService(name)

    def request(self, service, operation, params, arrays=None):
        request = self.service(service).createRequest(operation)
        for key, value in params.items():
            request.set(key, value)
        for key, values in (arrays or {}).items():
            for value in values:
                request.getElement(key).appendValue(value)
        queue = self.api.EventQueue()
        correlation = self.session.sendRequest(request, eventQueue=queue)
        deadline = time.monotonic()+45
        messages = []
        try:
            while time.monotonic() < deadline:
                event = queue.nextEvent(1000)
                for msg in event:
                    if str(msg.messageType()) == "RequestFailure":
                        raise RuntimeError(str(msg))
                    data = msg.toPy()
                    for error in ("responseError","fieldSearchError","instrumentListError"):
                        if error in data:
                            raise RuntimeError(str(data[error]))
                    messages.append(data)
                if event.eventType() == self.api.Event.RESPONSE:
                    return messages
            raise TimeoutError(operation+" exceeded 45 seconds")
        finally:
            self.session.cancel(correlation)

    def fields(self, query):
        key=("fields",query)
        if key not in self.cache:
            fields=[]
            for msg in self.request("//blp/apiflds","FieldSearchRequest",
                                    {"searchSpec":query,"returnFieldDocumentation":True}):
                for item in msg.get("fieldData",[]):
                    if "fieldInfo" in item:
                        info=item["fieldInfo"]
                        fields.append(dict(field=info.get("mnemonic",item.get("id")),
                                           description=info.get("description",""),
                                           documentation=info.get("documentation",""),
                                           datatype=info.get("datatype","")))
            self.cache[key]=fields
        return self.cache[key]

    def instruments(self, query):
        key=("instruments",query)
        if key not in self.cache:
            matches=[]
            for msg in self.request("//blp/instruments","instrumentListRequest",
                                    {"query":query,"yellowKeyFilter":"YK_FILTER_INDX","maxResults":20}):
                for item in msg.get("results",[]):
                    security=normalize_security(item.get("security",""))
                    matches.append(dict(security=security,description=item.get("description","")))
            self.cache[key]=matches
        return self.cache[key]

    def metadata(self, security, field):
        result={"security":security,"field":field}
        try:
            result["security_details"]=self.request("//blp/refdata","ReferenceDataRequest",{},
                {"securities":[security],"fields":["NAME","SECURITY_DES","CRNCY"]})
        except Exception as exc:
            result["security_metadata_error"]=str(exc)
        try:
            result["field_details"]=self.request("//blp/apiflds","FieldInfoRequest",
                {"returnFieldDocumentation":True},{"id":[field]})
        except Exception as exc:
            result["field_metadata_error"]=str(exc)
        return result

    def history(self, security, field, start, end):
        rows=[]
        for msg in self.request("//blp/refdata","HistoricalDataRequest",
                {"startDate":start.replace("-",""),"endDate":end.replace("-",""),
                 "periodicitySelection":"DAILY","nonTradingDayFillOption":"ACTIVE_DAYS_ONLY"},
                {"securities":[security],"fields":[field]}):
            data=msg.get("securityData",{})
            if "securityError" in data:
                raise RuntimeError(str(data["securityError"]))
            if data.get("fieldExceptions"):
                raise RuntimeError(str(data["fieldExceptions"]))
            for item in data.get("fieldData",[]):
                date=item.get("date")
                if isinstance(date,(dt.datetime,dt.date)):
                    date=date.isoformat()[:10]
                else:
                    date=str(date)[:10]
                dt.date.fromisoformat(date)
                value=item.get(field)
                if value is not None:
                    value=float(value)
                    if not math.isfinite(value):
                        raise ValueError("Non-finite value")
                rows.append({"date":date,"value":value})
        if not any(r["value"] is not None for r in rows):
            raise RuntimeError("No numeric historical observations")
        return rows

def candidate_pairs(client, spec, result):
    declared=[]
    fields=[]
    instruments=[]
    if spec.get("security") and spec.get("field"):
        declared.append((normalize_security(spec["security"]),spec["field"]))
    for field in spec.get("fields",[]):
        declared.append((normalize_security(spec["security"]),field))
    if spec.get("field_search"):
        try:
            matches=client.fields(spec["field_search"])
            result["field_search_results"]=matches
            for item in matches:
                if eligible_field(spec,item):
                    fields.append((normalize_security(spec["security"]),item["field"]))
        except Exception as exc:
            result["field_search_error"]=str(exc)
    if spec.get("instrument_search"):
        try:
            matches=client.instruments(spec["instrument_search"])
            result["instrument_search_results"]=matches
            for item in matches:
                if eligible_instrument(spec,item):
                    instruments.append((normalize_security(item["security"]),"PX_LAST"))
        except Exception as exc:
            result["instrument_search_error"]=str(exc)
    # Exchange count instruments precede Composite-member fields, avoiding a full
    # candidate budget consumed by generic or inappropriate field search results.
    pairs=declared+(instruments+fields if spec.get("kind")=="count" else fields+instruments)
    return list(dict.fromkeys(pairs))[:4]


def test_spec(client, spec, start, end, output):
    result=dict(id=spec["id"],definition=spec.get("definition",""),attempts=[])
    required_start=max(start,spec.get("expected_start",start))
    required_end=min(end,spec.get("expected_end",end))
    if required_start>required_end:
        result.update(status="OUTSIDE_REQUEST",reason="Required series window does not overlap requested dates.")
        return result
    candidates=candidate_pairs(client,spec,result)
    if not candidates:
        result.update(status="UNRESOLVED",reason="No eligible mapping found. Search output/errors are saved in the report; confirm using FLDS/SECF in Bloomberg.")
        return result
    for number,(security,field) in enumerate(candidates,1):
        attempt=dict(security=security,field=field)
        result["attempts"].append(attempt)
        print(f"  Candidate {number}/{len(candidates)}: {security} / {field}",flush=True)
        try:
            # Probe a small sample near this series' requested end (VIXC uses Jan 2020).
            sample_start=max(required_start,(dt.date.fromisoformat(required_end)-dt.timedelta(days=45)).isoformat())
            try:
                sample=client.history(security,field,sample_start,required_end)
                print(f"    Sample received: {len(sample)} rows. Pulling required history ...",flush=True)
            except RuntimeError as exc:
                if "No numeric historical observations" not in str(exc):
                    raise
                print("    No recent sample; pulling full window to check for older/stale history.",flush=True)
            rows=client.history(security,field,required_start,required_end)
            coverage=check_history(rows,spec,start,end)
            if "COUNTS_NOT_NONNEGATIVE_INTEGERS" in coverage.get("issues",[]):
                raise RuntimeError("Candidate is not a nonnegative integer count; trying another mapping.")
            if coverage["numeric_rows"]==0:
                raise RuntimeError("No numeric observations in required window")
            safe_id=spec["id"]
            if not re.fullmatch(r"[A-Za-z0-9_]+",safe_id):
                raise ValueError("Unsafe dataset id")
            (output/"raw").mkdir(parents=True,exist_ok=True)
            target=output/"raw"/(safe_id+".csv")
            with target.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.DictWriter(handle,fieldnames=["date","value"])
                writer.writeheader()
                writer.writerows(rows)
            verified=spec.get("verified",False) and security==spec.get("security") and field==spec.get("field")
            status="PASS" if verified and coverage["status"]=="RANGE_OK" else "REVIEW"
            metadata=client.metadata(security,field)
            attempt["status"]="DOWNLOADED"
            result.update(status=status,security=security,field=field,coverage=coverage,
                definition_verified=bool(verified),metadata=metadata,
                raw_file=str(target),sample=sorted([r for r in rows if r["value"] is not None],key=lambda r:r["date"])[-3:],
                reason="Numeric history downloaded. "+("Previously verified mapping." if verified else "Candidate definition, universe, units and benchmark choice require review; inspect saved Bloomberg documentation."))
            return result
        except Exception as exc:
            attempt.update(status="FAIL",error=str(exc))
            print("    [FAIL] "+str(exc),flush=True)
    result.update(status="FAIL",reason="All candidate historical pulls failed; see attempts and search metadata.")
    return result

def run_checks(start="2010-01-01",end=None,config=None,output=None,client_factory=BloombergClient):
    end=end or yesterday()
    config=Path(config) if config else ROOT/"bloomberg-series.json"
    output=Path(output) if output else ROOT/"data-access-results"
    print("\nBLOOMBERG - ALL DATASET CHECKS",flush=True)
    print(f"Requested: {start} -> {end} (default excludes today's unfinished session)",flush=True)
    report=dict(tested_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),start=start,end=end,results=[])
    try:
        specs=json.loads(config.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        report.update(config_error=str(exc))
        print(f"[CONFIG ERROR] {exc}. Extract the ZIP and keep bloomberg-series.json beside this script.",flush=True)
        save_report(output,"bloomberg-report.json",report)
        return report
    client=None
    try:
        print("[CONNECTING] Bloomberg localhost:8194 ...",flush=True)
        client=client_factory()
        report["connection_status"]="CONNECTED"
        print("[CONNECTED] Starting all configured candidate/discovery checks.",flush=True)
    except Exception as exc:
        report.update(connection_status="BLOCKED",connection_error=str(exc))
        print("[BLOCKED] "+str(exc),flush=True)
    try:
        for index,spec in enumerate(specs,1):
            print(f"\n[{index}/{len(specs)}] {spec['id']}: {spec.get('definition','')}",flush=True)
            if client is None:
                result=dict(id=spec["id"],status="BLOCKED",reason=report["connection_error"])
            else:
                try:
                    result=test_spec(client,spec,start,end,output)
                except Exception as exc:
                    result=dict(id=spec["id"],status="FAIL",reason=str(exc))
            report["results"].append(result)
            show_result(result)
            # Checkpoint after every dataset so interrupted runs retain completed work.
            output.mkdir(parents=True,exist_ok=True)
            (output/"bloomberg-report.json").write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
    finally:
        if client is not None:
            client.close()
    report["known_gap"]="Assignment notes Canadian VIXC/VIXI gap in 2020-21. Separate series are never spliced or filled by this checker."
    save_report(output,"bloomberg-report.json",report)
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start",default="2010-01-01")
    parser.add_argument("--end",default=yesterday())
    parser.add_argument("--config",type=Path,default=ROOT/"bloomberg-series.json")
    args=parser.parse_args(argv)
    dt.date.fromisoformat(args.start)
    dt.date.fromisoformat(args.end)
    if args.start>args.end:
        parser.error("Start date must precede end date")
    report=run_checks(args.start,args.end,args.config)
    return 0 if report["results"] and all(r["status"]=="PASS" for r in report["results"]) else 1

if __name__=="__main__":
    exit_code=main()
    if "IPython" not in sys.modules:
        raise SystemExit(exit_code)
