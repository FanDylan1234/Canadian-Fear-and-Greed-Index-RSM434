import base64
from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from index_engine.buildindicatorsfromdata import COMPONENTS, build_index
from index_engine.loadpulleddata import load_config
from index_engine.sandbox import custom_index, parse_polls, poll_scores
from test_index import fixture


def upload(text):
    return "data:text/csv;base64," + base64.b64encode(text.encode()).decode()


class SandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build_index(fixture(), load_config())

    def test_defaults_and_arbitrary_mix_leave_all_baseline_data_unchanged(self):
        before = deepcopy(self.result)
        history, _, weights, _ = custom_index(self.result, list(COMPONENTS), dict.fromkeys(COMPONENTS, 1))
        np.testing.assert_allclose(history["index"], before.history["index"])
        np.testing.assert_allclose(weights[list(COMPONENTS)], before.weights)
        custom, _, weights, _ = custom_index(self.result, ["momentum", "credit"], {"momentum": 3, "credit": 1})
        expected = before.scores.momentum * .75 + before.scores.credit * .25
        np.testing.assert_allclose(custom["index"], expected)
        np.testing.assert_allclose(weights.sum(axis=1), 1)
        for field in ("history", "scores", "signals", "weights", "inputs"):
            pd.testing.assert_frame_equal(getattr(self.result, field), getattr(before, field))

    def test_zero_missing_removed_and_single_indicator(self):
        for selected, relative in (([], {}), (["momentum"], {"momentum": 0}), (["confidence"], {"confidence": 1})):
            history, _, weights, _ = custom_index(self.result, selected, relative)
            self.assertTrue(history["index"].isna().all())
            self.assertTrue(weights.eq(0).all().all())
        changed = deepcopy(self.result)
        changed.scores.loc[changed.scores.index[-1], "credit"] = np.nan
        history, _, weights, _ = custom_index(changed, ["credit", "momentum"], {"credit": 9, "momentum": 1})
        self.assertEqual(history["index"].iloc[-1], changed.scores.momentum.iloc[-1])
        self.assertEqual(weights.momentum.iloc[-1], 1)
        self.assertEqual(weights.credit.iloc[-1], 0)
        for bad in (-1, 101, float("inf")):
            with self.assertRaises(ValueError):
                custom_index(changed, ["credit"], {"credit": bad})

    def test_weekly_ranking_publication_lag_staleness_and_no_future_leak(self):
        dates = pd.date_range("2011-01-03", periods=27, freq="7D")
        records = [{"release_date": str(date.date()), "confidence": float(i + 30)} for i, date in enumerate(dates)]
        calendar = pd.bdate_range(dates[0], dates[-1] + pd.Timedelta(days=20))
        scores, releases = poll_scores(records, calendar)
        self.assertTrue(scores.confidence.loc[:dates[-1]].isna().all())
        first = dates[-1] + pd.Timedelta(days=1)
        self.assertEqual(scores.confidence.loc[first], 100)
        self.assertEqual(releases.confidence.loc[first], dates[-1])
        self.assertEqual(scores.confidence.loc[dates[-1] + pd.Timedelta(days=14)], 100)
        self.assertTrue(scores.confidence.loc[dates[-1] + pd.Timedelta(days=15):].isna().all())
        extended = records + [{"release_date": str((dates[-1] + pd.Timedelta(days=7)).date()), "confidence": 0.}]
        new, _ = poll_scores(extended, calendar)
        pd.testing.assert_series_equal(scores.confidence.loc[:first], new.confidence.loc[:first])
        self.assertEqual(new.confidence.loc[dates[-1] + pd.Timedelta(days=8)], 0)
        history, _, weights, _ = custom_index(self.result, ["confidence"], {"confidence": 5}, records)
        self.assertEqual(history.loc[first, "index"], 100)
        self.assertEqual(weights.loc[first, "confidence"], 1)

    def test_csv_validation_does_not_accept_invalid_or_daily_repeated_polls(self):
        records = parse_polls(upload("release_date,confidence,pocketbook\n2011-01-10,52,\n2011-01-03,50,51\n"))
        self.assertEqual(records[0]["release_date"], "2011-01-03")
        self.assertIsNone(records[1]["pocketbook"])
        for content in (
            "date,value\n2011-01-03,50\n",
            "release_date,confidence\n2011-01-03,101\n",
            "release_date,confidence\n2011-01-03,inf\n",
            "release_date,confidence\n2011-01-03,no\n",
            "release_date,confidence\n2011-01-03,50\n2011-01-03,51\n",
            "release_date,confidence\n2011-01-03,50\n2011-01-04,50\n",
            "release_date,confidence\n2011-02-30,50\n",
            "release_date,confidence\n2999-01-01,50\n",
            "release_date,confidence\n2011-01-03,\n",
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_polls(upload(content))
        with self.assertRaises(ValueError):
            parse_polls("bad-base64")


if __name__ == "__main__":
    unittest.main()
