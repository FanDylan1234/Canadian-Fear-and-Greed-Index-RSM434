"""Offline validation of coverage rules and candidate/error handling.
These tests do not establish Bloomberg entitlements.
"""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_checks import check_history
from pull_bloomberg import test_spec, run_checks, BloombergClient

def rows(start,end,value=20):
    result=[]
    date=dt.date.fromisoformat(start)
    while date.isoformat()<=end:
        if date.weekday()<5:
            result.append({"date":date.isoformat(),"value":value+len(result)/100})
        date+=dt.timedelta(days=1)
    return result

class FakeClient:
    def __init__(self):
        self.closed=False
    def fields(self,query):
        raise RuntimeError("Field discovery not entitled")
    def instruments(self,query):
        return []
    def history(self,security,field,start,end):
        if security=="BAD Index":
            raise RuntimeError("NOT_ENTITLED")
        return rows(start,end)
    def metadata(self,security,field):
        return {"security":security,"field":field,"documentation":"test only"}
    def close(self):
        self.closed=True

class Checks(unittest.TestCase):
    def test_late_history_and_missing_internal_period_are_flagged(self):
        data=rows("2010-03-01","2010-12-31")
        data=[r for r in data if not "2010-06-01"<=r["date"]<="2010-07-01"]
        c=check_history(data,{},"2010-01-01","2010-12-31")
        self.assertIn("STARTS_LATE",c["issues"])
        self.assertIn("LONG_INTERNAL_GAPS",c["issues"])

    def test_legacy_vix_does_not_need_history_after_cessation(self):
        c=check_history(rows("2019-01-01","2020-01-31"),
            {"expected_start":"2010-10-01","expected_end":"2020-01-31"},"2019-01-01","2026-10-21")
        self.assertEqual(c["status"],"RANGE_OK")
        self.assertEqual(c["expected_end"],"2020-01-31")

    def test_count_cannot_be_a_price_or_percentage(self):
        c=check_history([{"date":"2026-10-01","value":3.25}],{"kind":"count"},
                        "2026-10-01","2026-10-01")
        self.assertIn("COUNTS_NOT_NONNEGATIVE_INTEGERS",c["issues"])

    def test_candidate_download_is_never_automatic_definition_pass(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            result=test_spec(FakeClient(),{"id":"candidate","security":"TEST Index","field":"PX_LAST",
                "field_search":"example","verified":False},"2026-09-01","2026-10-01",Path(directory))
        self.assertEqual(result["status"],"REVIEW")
        self.assertIn("field_search_error",result)
        self.assertTrue(result["coverage"]["numeric_rows"]>0)

    def test_failure_does_not_stop_later_dataset_and_session_closes(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory)
            specs=[{"id":"denied","security":"BAD Index","field":"PX_LAST"},
                   {"id":"good","security":"GOOD Index","field":"PX_LAST","verified":True}]
            config=root/"specs.json"
            config.write_text(json.dumps(specs),encoding="utf-8")
            client=FakeClient()
            result=run_checks("2026-09-01","2026-10-01",config,root,lambda:client)
            self.assertEqual([r["status"] for r in result["results"]],["FAIL","PASS"])
            self.assertTrue(client.closed)

    def test_history_rejects_security_and_field_errors(self):
        client=BloombergClient.__new__(BloombergClient)
        for message in [
            {"securityData":{"securityError":{"message":"bad ticker"}}},
            {"securityData":{"fieldExceptions":[{"fieldId":"BAD"}]}}
        ]:
            client.request=lambda *a, message=message, **kw:[message]
            with self.assertRaises(RuntimeError):
                client.history("TEST","BAD","2026-01-01","2026-02-01")

    def test_history_keeps_nulls_and_dates(self):
        client=BloombergClient.__new__(BloombergClient)
        client.request=lambda *a,**kw:[{"securityData":{"fieldData":[
            {"date":dt.date(2026,1,2),"PX_LAST":20},{"date":dt.date(2026,1,5),"PX_LAST":None}]}}]
        data=client.history("TEST","PX_LAST","2026-01-01","2026-02-01")
        self.assertEqual(data,[{"date":"2026-01-02","value":20.0},{"date":"2026-01-05","value":None}])

if __name__=="__main__":
    unittest.main()
