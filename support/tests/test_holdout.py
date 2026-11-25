import json
import unittest

import numpy as np
import pandas as pd

from index_engine.holdout import (
    ALLOCATION, BASELINE, BENCHMARK_EQUITY, CALIBRATION_FILE, CUTOFF, HORIZONS, SWITCH_COST, episode_table,
    evaluate, fit_calibration, forward_outcomes, quintiles, run_backtest,
)
from index_engine.buildindicatorsfromdata import build_index
from test_index import fixture


class HoldoutTests(unittest.TestCase):
    def test_forward_window_starts_after_signal_and_requires_complete_path(self):
        rng = np.random.default_rng(37)
        levels = pd.Series(100 * np.exp(rng.normal(0, .01, 200).cumsum()),
                           index=pd.bdate_range("2020-01-02", periods=200))
        levels.iloc[10] = np.nan
        actual = forward_outcomes(levels)
        for m, h in HORIZONS.items():
            self.assertTrue(pd.isna(actual[f"return_{m}m"].iloc[0]))
            self.assertTrue(actual[f"vol_{m}m"].iloc[-h:].isna().all())
            path = levels.iloc[12:13+h].to_numpy()
            self.assertEqual(actual[f"end_{m}m"].iloc[12], levels.index[12+h])
            self.assertAlmostEqual(actual[f"return_{m}m"].iloc[12], path[-1] / path[0] - 1)
            daily = path[1:] / path[:-1] - 1
            self.assertAlmostEqual(actual[f"vol_{m}m"].iloc[12], daily.std(ddof=1) * np.sqrt(252))

    def test_calibration_is_invariant_to_holdout_scores_and_outcomes(self):
        dates = pd.bdate_range("2018-01-01", "2020-06-30")
        x = np.arange(len(dates))
        history = pd.DataFrame({"index": x % 101, "vix_score": (2*x) % 101,
                                "tsx_total_return": 100 + x}, index=dates)
        before = fit_calibration(history)
        history.loc[dates > CUTOFF] = 10000
        self.assertEqual(before, fit_calibration(history))
        for m, h in HORIZONS.items():
            model = before["models"]["index"]["forecasts"]
            self.assertEqual(sum(row["n"] for row in model if row["months"] == m),
                             len(history.loc[:CUTOFF]) - h)
        q = quintiles(pd.Series([24., 25., 50., 75., 90., np.nan]), [25, 50, 65, 75])
        self.assertEqual(q.iloc[:5].tolist(), [1, 1, 2, 4, 5])
        self.assertTrue(pd.isna(q.iloc[-1]))

    def test_sentiment_mix_versus_60_40_trades_at_next_joint_close(self):
        dates = pd.bdate_range("2020-01-02", periods=8)
        h = pd.DataFrame({"index": [75, 80, 90, np.nan, 25, 20, np.nan, 50],
                          "tsx_total_return": [100, 110, 121, 133.1, 120, 110, 110, 121],
                          "bond_total_return": [100, 100, np.nan, 100, 105, 110, 120, 115]}, index=dates)
        ledger, perf = run_backtest(h)
        # 75 is Greed (60/40), 80 is Extreme greed (bonds), 25 is Fear (60/40), 20 is Extreme fear (equities).
        self.assertEqual(ledger.index[ledger.switched].tolist(), [dates[3], dates[5], dates[6]])
        self.assertEqual(ledger.equity_after_close.tolist(), [.6, .6, 0, 0, .6, 1, 1])
        self.assertEqual(ledger.loc[dates[3], "signal_date"], dates[2])
        self.assertEqual(ledger.loc[dates[3], "signal_regime"], "Extreme greed")
        self.assertTrue((ledger.loc[ledger.switched, "signal_date"] < ledger.index[ledger.switched]).all())

        def replay(targets):
            weight, wealth = BENCHMARK_EQUITY, 100.
            levels = ledger[["tsx_total_return", "bond_total_return"]].to_numpy()
            for (e0, b0), (e1, b1), target in zip(levels, levels[1:], targets[1:]):
                re, rb = e1 / e0 - 1, b1 / b0 - 1
                gross = weight * re + (1 - weight) * rb
                drifted = weight * (1 + re) / (1 + gross)
                wealth *= (1 + gross) * (1 - SWITCH_COST * abs(target - drifted))
                weight = target
            return wealth

        perf = perf.set_index("portfolio")
        self.assertAlmostEqual(ledger.strategy_wealth.iloc[-1], replay(ledger.equity_after_close.tolist()))
        self.assertAlmostEqual(perf.loc["Sentiment strategy"].end_wealth, ledger.strategy_wealth.iloc[-1])
        self.assertAlmostEqual(perf.loc["60/40 strategy"].end_wealth, replay([BENCHMARK_EQUITY] * len(ledger)))
        self.assertAlmostEqual(perf.loc["TSX buy and hold"].end_wealth, 121)
        daily = ledger.equity_return.iloc[1:]
        vol = daily.std(ddof=1) * np.sqrt(252)
        self.assertAlmostEqual(perf.loc["TSX buy and hold"].volatility, vol)
        self.assertAlmostEqual(perf.loc["TSX buy and hold"].sharpe, daily.mean() * 252 / vol)
        self.assertEqual(ALLOCATION["Extreme fear"], 1)
        self.assertEqual(ALLOCATION["Extreme greed"], 0)

    def test_no_breach_and_no_observations_are_distinct(self):
        h = pd.DataFrame({"index": [25., np.nan]}, index=pd.to_datetime(["2020-03-02", "2020-03-03"]))
        e = episode_table(h)
        self.assertEqual(e.scored.tolist(), [1, 0])
        self.assertEqual(e.fear_days.tolist(), [0, 0])
        self.assertTrue(e.first_fear.isna().all())

    def test_matched_forecasts_and_separate_frozen_design(self):
        inputs = fixture()
        inputs.index = pd.bdate_range("2017-01-02", periods=len(inputs))
        inputs.loc[inputs.index[-240:-225], "fred_vix"] = np.nan
        altered = dict(BASELINE, rank_window=160)
        live = build_index(inputs, altered)
        frozen = build_index(inputs, BASELINE)
        r = evaluate(live, inputs, altered)
        pd.testing.assert_series_equal(r.audit["index"], frozen.history["index"])
        self.assertFalse(r.audit["index"].equals(live.history["index"]))
        self.assertEqual(r.calibration, json.loads(CALIBRATION_FILE.read_text()))
        for row in r.comparison.itertuples():
            cols = [f"{row.target}_{row.months}m", f"index_forecast_{row.target}_{row.months}m",
                    f"vix_score_forecast_{row.target}_{row.months}m"]
            matched = r.audit.loc[r.audit.period == "holdout", cols].dropna().to_numpy()
            self.assertEqual(len(matched), row.n)
            absolute_errors = abs(matched[:, 1:] - matched[:, :1])
            self.assertEqual((absolute_errors[:, 0] < absolute_errors[:, 1]).sum(), row.index_closer_days)
            for i, rmse in enumerate([row.index_rmse, row.vix_rmse], 1):
                self.assertAlmostEqual(np.linalg.norm(matched[:, 0] - matched[:, i]) / np.sqrt(row.n), rmse)
        self.assertTrue((r.audit.loc[:CUTOFF, "end_6m"].dropna() <= CUTOFF).all())


if __name__ == "__main__":
    unittest.main()
