"""Frozen baseline, supervised calibration, and chronological holdout evaluation."""

from dataclasses import dataclass
import hashlib
import json

import numpy as np
import pandas as pd

from .buildindicatorsfromdata import COMPONENTS, build_index
from .loadpulleddata import ROOT


CUTOFF = pd.Timestamp("2019-12-31")
HORIZONS = {1: 21, 3: 63, 6: 126}
SIGNALS = ("index", "vix_score")
TARGETS = ("return", "vol")
BASELINE = {
    "rank_window": 252, "rank_min_history": 126, "minimum_components": 5,
    "breadth_enabled": True, "display_start": "2010-01-01",
}
CALIBRATION_FILE = ROOT / "support" / "config" / "holdout-calibration.json"
SWITCH_COST = 0.001
EPISODES = {
    "March 2020": ("2020-03-01", "2020-03-31"),
    "Calendar 2022": ("2022-01-01", "2022-12-31"),
}


def forward_outcomes(levels):
    """At t, use the h daily simple returns (t, t+h], requiring a full path."""
    daily = levels.pct_change(fill_method=None)
    dates = levels.index.to_series()
    out = pd.DataFrame(index=levels.index)
    for months, h in HORIZONS.items():
        volatility = daily.rolling(h, min_periods=h).std(ddof=1).shift(-h)
        out[f"end_{months}m"] = dates.shift(-h)
        out[f"return_{months}m"] = (levels.shift(-h) / levels - 1).where(volatility.notna())
        out[f"vol_{months}m"] = volatility * np.sqrt(252)
    return out


def quintiles(scores, cuts):
    # Exact ties go to the lower bin. Also works for repeated breakpoints.
    values = np.searchsorted(cuts, scores.to_numpy(dtype=float), side="left") + 1
    return pd.Series(values, index=scores.index).where(scores.notna()).astype("Int64")


def training_fingerprint(train):
    fields = train.loc[:CUTOFF, [*SIGNALS, "tsx_total_return"]]
    return hashlib.sha256(fields.to_csv(float_format="%.12g", lineterminator="\n").encode()).hexdigest()


def fit_calibration(history):
    """Only labels which mature by the cutoff can enter either forecast model."""
    train = history.loc[:CUTOFF]
    outcomes = forward_outcomes(train.tsx_total_return)
    matched = train[list(SIGNALS)].notna().all(axis=1)
    models = {}
    for signal in SIGNALS:
        scores = train[signal].dropna()
        if scores.nunique() < 5:
            raise ValueError(f"Insufficient pre-2020 calibration history for {signal}")
        cuts = scores.quantile([0.2, 0.4, 0.6, 0.8]).tolist()
        bins = quintiles(train[signal], cuts)
        means = []
        for months in HORIZONS:
            ret, vol = f"return_{months}m", f"vol_{months}m"
            for q in range(1, 6):
                rows = outcomes.loc[matched & bins.eq(q), [ret, vol]].dropna()
                means.append(dict(months=months, quintile=q, n=len(rows),
                                  mean_return=rows[ret].mean() if len(rows) else None,
                                  mean_vol=rows[vol].mean() if len(rows) else None))
        models[signal] = dict(cuts=cuts, score_count=len(scores), forecasts=means)
    return dict(design="baseline-v1-2026-11-06", settings=BASELINE,
                components=list(COMPONENTS), training_first=train.index[0].date().isoformat(),
                train_end=CUTOFF.date().isoformat(), train_sha256=training_fingerprint(train),
                sessions_per_horizon=HORIZONS, models=models)


def forecast_tables(audit, calibration):
    predictions, comparisons = [], []
    hold = audit.index > CUTOFF
    for signal in SIGNALS:
        audit[f"{signal}_quintile"] = quintiles(audit[signal], calibration["models"][signal]["cuts"])
    bins = audit["index_quintile"]
    for months in HORIZONS:
        ret, vol = f"return_{months}m", f"vol_{months}m"
        for q in range(1, 6):
            group = audit.loc[hold & bins.eq(q), [ret, vol]].dropna()
            predictions.append(dict(months=months, quintile=q, n=len(group),
                                    mean_return=group[ret].mean(), mean_vol=group[vol].mean()))
        for target in TARGETS:
            actual = audit[f"{target}_{months}m"]
            forecasts = {}
            for signal in SIGNALS:
                model = calibration["models"][signal]["forecasts"]
                mapping = {r["quintile"]: r[f"mean_{target}"] for r in model if r["months"] == months}
                col = f"{signal}_forecast_{target}_{months}m"
                audit[col] = audit[f"{signal}_quintile"].map(mapping).astype(float).where(hold)
                forecasts[signal] = audit[col]
            paired = hold & actual.notna() & forecasts["index"].notna() & forecasts["vix_score"].notna()
            index_error = (forecasts["index"][paired] - actual[paired]).abs()
            vix_error = (forecasts["vix_score"][paired] - actual[paired]).abs()
            idx = np.sqrt(index_error.pow(2).mean())
            vix = np.sqrt(vix_error.pow(2).mean())
            comparisons.append(dict(months=months, target=target, n=int(paired.sum()),
                                    index_closer_days=int((index_error < vix_error).sum()),
                                    index_rmse=idx, vix_rmse=vix, advantage=vix-idx))
    return pd.DataFrame(predictions), pd.DataFrame(comparisons)


def episode_table(history):
    rows = []
    for label, (start, end) in EPISODES.items():
        window = history.loc[start:end, "index"]
        valid = window.dropna()
        fear = valid[valid < 25]
        rows.append(dict(episode=label, start=start, end=end, sessions=len(window), scored=len(valid),
                         fear_days=len(fear), first_fear=fear.index.min(), low=valid.min(),
                         low_date=valid.idxmin() if len(valid) else pd.NaT))
    return pd.DataFrame(rows)


def run_backtest(history):
    """A close signal can execute only at a later joint close, after marking the old holding."""
    hold = history.loc[history.index > CUTOFF, ["index", "tsx_total_return", "bond_total_return"]]
    ledger = hold.dropna(subset=["tsx_total_return", "bond_total_return"]).copy()
    if ledger.empty:
        return ledger, pd.DataFrame()
    # Start endowed with equities at the first investable close, with no pre-start orders.
    hold = hold.loc[ledger.index[0]:]
    target = pd.Series(np.nan, index=hold.index)
    target.loc[hold["index"] < 25] = 1
    target.loc[hold["index"] > 75] = 0
    eligible = target.ffill().shift()
    ledger["signal_date"] = hold.index.to_series().where(target.notna()).ffill().shift()
    ledger["signal_score"] = hold["index"].where(target.notna()).ffill().shift()
    ledger["equity_after_close"] = eligible.reindex(ledger.index).fillna(1).astype(int)
    prior = ledger["equity_after_close"].shift(fill_value=1)
    ledger["equity_during_interval"] = prior
    ledger["switched"] = prior.ne(ledger["equity_after_close"])
    eq = ledger.tsx_total_return.pct_change(fill_method=None)
    bond = ledger.bond_total_return.pct_change(fill_method=None)
    ledger["equity_return"], ledger["bond_return"] = eq, bond
    ledger["gross_return"] = eq.where(prior.eq(1), bond)
    ledger["cost_fraction"] = SWITCH_COST * ledger["switched"]
    ledger["net_return"] = (1 + ledger.gross_return) * (1 - ledger.cost_fraction) - 1
    paths = {"Rule after costs": ("net_wealth", ledger.net_return),
             "Rule before costs": ("gross_wealth", ledger.gross_return),
             "TSX buy and hold": ("equity_wealth", eq),
             "Canada Aggregate buy and hold": ("bond_wealth", bond)}
    years = (ledger.index[-1] - ledger.index[0]).days / 365.2425
    performance = []
    for label, (column, returns) in paths.items():
        wealth = 100 * (1 + returns.fillna(0)).cumprod()
        ledger[column] = wealth
        performance.append(dict(portfolio=label, end_wealth=wealth.iloc[-1],
                                total_return=wealth.iloc[-1]/100 - 1,
                                cagr=(wealth.iloc[-1]/100)**(1/years)-1 if years else np.nan,
                                max_drawdown=(wealth / wealth.cummax() - 1).min()))
    return ledger, pd.DataFrame(performance)


@dataclass
class Research:
    calibration: dict
    audit: pd.DataFrame
    prediction: pd.DataFrame
    comparison: pd.DataFrame
    episodes: pd.DataFrame
    ledger: pd.DataFrame
    performance: pd.DataFrame
    inputs: pd.DataFrame


def evaluate(result, inputs, live_config):
    calibration = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    if calibration["settings"] != BASELINE or calibration["components"] != list(COMPONENTS):
        raise ValueError("Frozen design and calibration disagree")
    if any(live_config.get(k) != v for k, v in BASELINE.items()):
        result = build_index(inputs, BASELINE)
    history = result.history
    audit = history.join(result.scores.add_prefix("score_")).join(result.weights.add_prefix("weight_"))
    audit["us_vix_close"] = result.inputs["fred_vix"]
    audit["period"] = np.where(audit.index <= CUTOFF, "training", "holdout")
    # Split before shifting so no 2020 realization leaks into a 2019 training row.
    parts = [forward_outcomes(group.tsx_total_return) for _, group in audit.groupby("period")]
    audit = audit.join(pd.concat(parts))
    prediction, comparison = forecast_tables(audit, calibration)
    ledger, performance = run_backtest(history)
    return Research(calibration, audit, prediction, comparison, episode_table(history),
                    ledger, performance, inputs.loc[inputs.tsx_price.notna()])
