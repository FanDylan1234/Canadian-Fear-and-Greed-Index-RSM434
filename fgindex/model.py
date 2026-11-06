"""Causal daily index. Missing data never become zero or backfilled observations."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

COMPONENTS = {
    "momentum": ("Market momentum", "TSX versus its prior 125-session average", "A market above its recent trend indicates greater risk appetite."),
    "strength": ("Stock price strength", "20-session mean of new 52-week highs minus lows", "More stocks making new highs suggests broader confidence."),
    "breadth": ("Market breadth", "20-session mean of (advancers − decliners) / total", "Participation across the same stock universe confirms market direction."),
    "options": ("Put / call options", "5-session mean of Montréal equity put/call ratio", "Higher demand for puts signals greater demand for protection."),
    "volatility": ("Market volatility", "Canadian implied volatility; disclosed US VIX fallback", "Higher expected volatility signals fear. Each source is ranked separately."),
    "credit": ("Credit demand", "Canadian investment-grade corporate OAS", "Wider credit spreads indicate lower willingness to take credit risk."),
    "safe_haven": ("Safe-haven demand", "20-session stock minus aggregate-bond total return", "Equity outperformance of bonds indicates greater risk appetite."),
}


def regime(value):
    if pd.isna(value):
        return "Unavailable"
    if value < 25:
        return "Extreme fear"
    if value < 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme greed"


def past_percentile(series, window=252, minimum=126):
    """Rank today against finite values in the prior N sessions; ties get midrank."""
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    for i, value in enumerate(values):
        prior = values[max(0, i-window):i]
        prior = prior[np.isfinite(prior)]
        if np.isfinite(value) and len(prior) >= minimum:
            out[i] = 100 * ((prior < value).sum() + .5 * (prior == value).sum()) / len(prior)
    return pd.Series(out, index=series.index)


def mask_stale(series, limit=10):
    """Only mask from the Nth identical quote onward, never retroactively."""
    runs = series.groupby(series.ne(series.shift()).cumsum()).cumcount() + 1
    return series.mask(runs >= limit)


def aggregate(scores, minimum=5):
    count = scores.notna().sum(axis=1)
    valid = count >= minimum
    weights = scores.notna().div(count.replace(0, np.nan), axis=0).where(valid, 0).fillna(0)
    index = scores.mean(axis=1).where(valid)
    return index, weights, count


@dataclass
class IndexResult:
    history: pd.DataFrame
    signals: pd.DataFrame
    scores: pd.DataFrame
    weights: pd.DataFrame
    inputs: pd.DataFrame


def build_index(inputs, config):
    data = inputs.copy().sort_index()
    if data.index.has_duplicates:
        raise ValueError("Duplicate trading dates")
    # The observed TSX price dates are the session calendar. No synthetic holiday rows.
    data = data.loc[data.tsx_price.notna()]
    def get(name):
        return data.get(name, pd.Series(np.nan, index=data.index, dtype=float))
    price = get("tsx_price")
    signals = pd.DataFrame(index=data.index)
    signals["momentum"] = price / price.shift(1).rolling(125, min_periods=125).mean() - 1
    signals["strength"] = (get("tsx_52week_highs") - get("tsx_52week_lows")).rolling(20, min_periods=20).mean()
    adv, dec = get("tsx_advancing"), get("tsx_declining")
    signals["breadth"] = ((adv-dec)/(adv+dec).replace(0, np.nan)).rolling(20, min_periods=20).mean()
    if not config["breadth_enabled"]:
        signals["breadth"] = np.nan
    signals["options"] = get("mx_equity_put_call").rolling(5, min_periods=5).mean()
    signals["credit"] = get("canada_ig_credit_spread")
    signals["safe_haven"] = get("tsx_total_return").pct_change(20, fill_method=None) - get("canada_bond_total_return").pct_change(20, fill_method=None)
    def rank(s):
        return past_percentile(s, config["rank_window"], config["rank_min_history"])
    scores = pd.DataFrame({c: rank(signals[c]) for c in signals}, index=data.index)
    for c in ("options", "credit"):
        scores[c] = 100 - scores[c]
    # Never percentile-rank a splice of differently defined volatility levels.
    source = pd.Series("Unavailable", index=data.index)
    vol_score = pd.Series(np.nan, index=data.index)
    vol_level = pd.Series(np.nan, index=data.index)
    # Increasing priority: US fallback, legacy Canadian, replacement Canadian.
    for name, label in [("fred_vix", "US VIX fallback"), ("canada_vixc_history", "VIXC"), ("canada_vixi_history", "VIXI")]:
        series = mask_stale(get(name))
        if label == "VIXI":
            series = series.where(data.index >= "2021-04-26")
        elif label == "VIXC":
            series = series.where(data.index <= "2020-01-22")
        score = 100 - rank(series)
        use = score.notna()
        vol_score.loc[use], vol_level.loc[use], source.loc[use] = score[use], series[use], label
    signals["volatility"] = vol_level
    scores["volatility"] = vol_score
    signals, scores = signals[list(COMPONENTS)], scores[list(COMPONENTS)]
    index, weights, count = aggregate(scores, config["minimum_components"])
    history = pd.DataFrame({"index": index, "regime": index.map(regime), "active_components": count,
                            "volatility_source": source, "tsx_price": price,
                            "tsx_total_return": get("tsx_total_return"), "bond_total_return": get("canada_bond_total_return"),
                            "vix_score": 100-rank(mask_stale(get("fred_vix")))})
    keep = data.index >= config["display_start"]
    return IndexResult(history.loc[keep], signals.loc[keep], scores.loc[keep], weights.loc[keep], data.loc[keep])
