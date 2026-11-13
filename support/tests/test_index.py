import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from index_engine.data import load_config, read_inputs
from index_engine.model import past_percentile, aggregate, mask_stale, build_index, regime
from index_engine.live import quote_snapshot


def fixture():
    dates = pd.bdate_range("2008-01-01", "2012-12-31")
    x = np.arange(len(dates))
    return pd.DataFrame({"tsx_price": 100+ .04*x + 3*np.sin(x/13),
                         "tsx_total_return": 100+.07*x+3*np.sin(x/13),
                         "canada_bond_total_return": 100+.02*x+np.sin(x/39),
                         "tsx_advancing": 100+(x % 40), "tsx_declining": 100-(x % 40),
                         "tsx_52week_highs": x % 17, "tsx_52week_lows": x % 11,
                         "mx_equity_put_call": .5+.1*np.sin(x/7),
                         "canada_ig_credit_spread": 100+20*np.sin(x/31),
                         "canada_vixc_history": 20+np.sin(x/19),
                         "canada_vixi_history": np.nan, "fred_vix": 25+np.sin(x/11)}, index=dates)


class IndexTests(unittest.TestCase):
    def test_past_only_rank_and_ties(self):
        score = past_percentile(pd.Series([10., 10., 20., 5.]), 2, 2)
        self.assertTrue(score.iloc[:2].isna().all())
        self.assertEqual(score.iloc[2], 100)
        self.assertEqual(score.iloc[3], 0)
        self.assertEqual(past_percentile(pd.Series([1., 1., 1.]), 2, 2).iloc[-1], 50)

    def test_equal_weights_and_minimum(self):
        scores = pd.DataFrame([[10.]*7, [10.]*6+[np.nan], [10.]*5+[np.nan]*2, [10.]*4+[np.nan]*3])
        index, weights, count = aggregate(scores)
        np.testing.assert_allclose(weights.sum(axis=1), [1, 1, 1, 0])
        self.assertEqual(weights.iloc[1, 0], 1/6)
        self.assertEqual(weights.iloc[1, 6], 0)
        self.assertTrue(pd.isna(index.iloc[-1]))

    def test_future_changes_cannot_rewrite_past(self):
        source = fixture()
        config = load_config()
        first = build_index(source, config)
        date = pd.Timestamp("2011-08-01")
        source.loc[source.index > date, "tsx_price"] *= 4
        source.loc[source.index > date, "canada_vixc_history"] = 150
        source.loc[source.index > date, "mx_equity_put_call"] *= 10
        second = build_index(source, config)
        pd.testing.assert_frame_equal(first.scores.loc[:date], second.scores.loc[:date])
        pd.testing.assert_series_equal(first.history.loc[:date, "index"], second.history.loc[:date, "index"])

    def test_zero_breadth_denominator_is_unavailable(self):
        source = fixture()
        source.loc[source.index[-1], ["tsx_advancing", "tsx_declining"]] = 0
        result = build_index(source, load_config())
        self.assertTrue(pd.isna(result.scores.breadth.iloc[-1]))
        self.assertEqual(result.weights.breadth.iloc[-1], 0)

    def test_volatility_fallback_and_no_future_launch_values(self):
        source = fixture()
        source["canada_vixi_history"] = 14 + np.sin(np.arange(len(source))/9)
        source.loc[source.index[-1], "canada_vixc_history"] = np.nan
        result = build_index(source, load_config())
        self.assertEqual(result.history.volatility_source.iloc[-1], "US VIX fallback")
        self.assertNotIn("VIXI", result.history.volatility_source.unique())

    def test_stale_detection_is_causal_and_does_not_remove_earlier_quotes(self):
        result = mask_stale(pd.Series([12.]*12+[13.]))
        self.assertTrue(result.iloc[:9].notna().all())
        self.assertTrue(result.iloc[9:12].isna().all())
        self.assertEqual(result.iloc[-1], 13.)

    def test_2010_start_uses_preperiod_warmup(self):
        result = build_index(fixture(), load_config())
        self.assertEqual(str(result.history.index[0].date()), "2010-01-01")
        self.assertTrue(pd.notna(result.history["index"].iloc[0]))

    def test_missing_observation_not_forward_filled(self):
        source = fixture()
        source.loc[source.index[-1], "canada_ig_credit_spread"] = np.nan
        result = build_index(source, load_config())
        self.assertTrue(pd.isna(result.scores.credit.iloc[-1]))

    def test_venture_cache_excluded_despite_enabled_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.mkdir()
            for name in ("tsx_price", "tsx_advancing", "tsx_declining"):
                (raw / (name+".csv")).write_text("date,value\n2010-01-04,100\n2010-01-05,101\n")
            metadata = {"security_details": [{"securityData": [{"fieldData": {"NAME": "S&P/TSX Venture Composite"}}]}]}
            (root / "bloomberg-report.json").write_text(json.dumps({"results": [{"id": name, "definition_verified": True, "metadata": metadata} for name in ("tsx_advancing", "tsx_declining")]}))
            data, coverage = read_inputs(raw, load_config())
            self.assertTrue(data.tsx_advancing.isna().all())
            self.assertTrue(data.tsx_declining.isna().all())
            self.assertTrue(any("Venture" in row["status"] for row in coverage))

    def test_quote_timestamp_and_session_cleanup(self):
        class Client:
            closed = False
            def request(self, *a, **kw):
                return [{"securityData": [{"security": "SPTSX Index", "fieldData": {"PX_LAST": 123, "LAST_UPDATE_DT": "2026-11-06", "LAST_UPDATE": "16:00:00"}}]}]
            def close(self):
                self.closed = True
        client = Client()
        result = quote_snapshot(lambda: client)
        self.assertEqual(result["quotes"][0]["quote_date"], "2026-11-06")
        self.assertTrue(client.closed)

    def test_options_delay_carries_score_with_original_date(self):
        source = fixture()
        source.loc[source.index[-2:], "mx_equity_put_call"] = np.nan
        result = build_index(source, load_config())
        self.assertEqual(result.scores.options.iloc[-1], result.scores.options.iloc[-3])
        self.assertAlmostEqual(result.weights.options.iloc[-1], 1/7)
        self.assertEqual(result.history.options_score_date.iloc[-1], source.index[-3])
        self.assertTrue(result.history.options_carried_forward.iloc[-1])
        source["mx_equity_put_call"] = np.nan
        missing = build_index(source, load_config())
        self.assertTrue(missing.scores.options.isna().all())
        self.assertTrue((missing.weights.options == 0).all())

    def test_regime_boundaries(self):
        self.assertEqual([regime(x) for x in [0, 25, 45, 55, 75, 100]],
                         ["Extreme fear", "Fear", "Neutral", "Neutral", "Greed", "Extreme greed"])
        from index_engine.charts import color, BANDS
        colors = {label: shade for _, _, label, shade in BANDS}
        for value in (0, 25, 45, 55, 75, 100):
            self.assertEqual(color(value), colors[regime(value)])


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from index_engine.app import create_app
        from index_engine.pipeline import build
        from index_engine.service import DashboardService
        # Fully offline deterministic inputs; no dependency on licensed local exports.
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        source = fixture()
        cls.result = build_index(source, load_config())
        cls.service = DashboardService.__new__(DashboardService)
        cls.service.config = load_config()
        cls.service.snapshot = lambda: (cls.result, {"last_date": "2012-12-31", "coverage": []}, "Offline test", None, "Offline", False)
        cls.service.request_refresh = lambda: None
        cls.app = create_app(service=cls.service)
        cls.client = cls.app.server.test_client()

    def assert_clean_text(self, payload):
        # Inspect decoded HTTP data: JSON escaping must not hide broken text.
        text = str(payload)
        for broken in ("\u00c2", "\u00c3", "\u00e2\u20ac", "\u00e2\u2020", "\ufffd"):
            self.assertNotIn(broken, text)

    def test_dashboard_text_encoding(self):
        response = self.client.get("/")
        self.assertIn("charset=utf-8", response.content_type.lower())
        layout = self.client.get("/_dash-layout").get_json()
        self.assert_clean_text(layout)
        self.assertIn("Bloomberg \u00b7 Montr\u00e9al Exchange \u00b7 FRED", str(layout))
        from index_engine.charts import gauge
        self.assertIn("\u2014", str(gauge(float("nan")).to_plotly_json()))

    def test_dash_routes(self):
        for route in ("/", "/_dash-layout", "/_dash-dependencies", "/assets/style.css"):
            with self.client.get(route) as response:
                self.assertEqual(response.status_code, 200, route)
        self.assertEqual(self.client.get("/download/secrets").status_code, 404)

    def test_all_dashboard_callbacks(self):
        key = next(iter(self.app.callback_map))
        outputs = [{"id": name, "property": prop} for name, prop in [("page-content", "children"), ("status-banner", "children"), ("quote-strip", "children"), ("date-controls", "style"), ("refresh-button", "disabled"), ("render-key", "data")]]
        for view in ("overview", "timeline", "data", "methodology"):
            inputs = [{"id": name, "property": prop, "value": val} for name, prop, val in [("view", "value", view), ("ui-tick", "n_intervals", 0), ("refresh-button", "n_clicks", 0), ("date-range", "start_date", "2010-01-01"), ("date-range", "end_date", "2012-12-31"), ("weight-date", "date", "2011-01-01")]]
            response = self.client.post("/_dash-update-component", json={"output": key, "outputs": outputs, "inputs": inputs, "state": [{"id":"render-key","property":"data","value":None}], "changedPropIds": ["view.value"]})
            self.assertEqual(response.status_code, 200, response.data[:300])
            self.assertIn("page-content", response.json["response"])
            rendered = response.json["response"]
            self.assert_clean_text(rendered)
            page = rendered["page-content"]["children"]["props"]
            self.assertEqual(page["key"], view)
            self.assertEqual(page["data-view"], view)
            self.assertEqual("timeline-history" in str(page), view == "timeline")
            if view == "timeline":
                self.assertIn("Download history \u2193", str(rendered))
            if view in ("timeline", "data"):
                control_style = rendered["date-controls"]["style"]
                self.assertEqual(control_style["--timeline-display"], "flex" if view == "timeline" else "none")
                self.assertEqual(control_style["--weights-display"], "flex" if view == "data" else "none")
            unchanged = self.client.post("/_dash-update-component", json={
                "output": key, "outputs": outputs, "inputs": inputs,
                "state": [{"id":"render-key","property":"data","value":rendered["render-key"]["data"]}],
                "changedPropIds":["ui-tick.n_intervals"],
            })
            self.assertEqual(unchanged.status_code, 200)
            self.assertNotIn("page-content", unchanged.json["response"])


if __name__ == "__main__":
    unittest.main()

