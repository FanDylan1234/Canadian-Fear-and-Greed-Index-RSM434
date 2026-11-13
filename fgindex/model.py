"""Calculate the seven sentiment signals and their combined daily score."""

from dataclasses import dataclass
import numpy as np
import pandas as pd

COMPONENTS = {
    "momentum": (
        "Market momentum",
        "TSX versus its prior 125-session average",
        "We compare the TSX Composite with its average over the previous 125 trading sessions, roughly six months. A larger premium to that trend suggests investors are willing to pay more for equities; weakness below trend suggests less confidence. The distance from the average is ranked against its own recent history, so unusually strong momentum raises the greed score.\n\nMomentum describes the prevailing trend, not whether stocks are cheap or expensive. Earnings, interest rates and the TSX's sector mix can also drive prices, and strong trends can reverse.",
    ),
    "strength": (
        "Stock price strength",
        "20-session mean of new 52-week highs minus lows",
        "We subtract the number of Composite members making new 52-week lows from those making new 52-week highs, then average the difference over 20 sessions. A broad set of stocks breaking higher suggests confidence extends beyond a few large companies. More new lows suggests weakness is spreading. A higher net count relative to its recent history raises the greed score.\n\nThis measures participation at longer-term price extremes. It differs from daily breadth: a stock can rise today while remaining far below its yearly high. The count can also change as index membership and sector conditions change.",
    ),
    "breadth": (
        "Market breadth",
        "20-session mean of (advancers − decliners) / total",
        "We count advancing and declining TSX Composite members, divide their difference by their combined count, and average that ratio over 20 sessions. When many stocks rise together, buying is more widespread than when a few heavily weighted names lift the index. Stronger participation raises the greed score; widespread declines lower it.\n\nThe ratio normalizes for the number of stocks moving that day and excludes unchanged stocks. It gives each advancing or declining stock the same count, so it complements the capitalization-weighted index. It measures direction, not trading volume or the size of price moves.",
    ),
    "options": (
        "Put / call options",
        "5-session mean of Montréal equity put/call ratio",
        "We use the five-session average of the Montreal Exchange equity put/call ratio. Puts can protect against falling prices, while calls can provide upside exposure. More put activity relative to calls is therefore interpreted as greater demand for protection. The percentile score is inverted: an unusually high ratio lowers the greed score.\n\nOptions activity is not a direct vote on market direction: each trade has a buyer and seller, and hedging, covered calls and multi-leg strategies also affect the ratio. Smoothing reduces daily noise. When publication is delayed, the latest available calculated score remains included at equal weight, with its original date shown.",
    ),
    "volatility": (
        "Market volatility",
        "Canadian implied volatility; disclosed US VIX fallback",
        "Implied volatility reflects the size of future moves priced into options, not a forecast that prices must fall. Elevated readings often accompany uncertainty and expensive downside protection, so unusually high volatility lowers the greed score. Low readings indicate calmer pricing, although they can also reflect complacency.\n\nWe rank VIXC and VIXI separately because their definitions differ. US VIX is used only when Canadian scores are unavailable or warming up, and is identified in the history. It reflects US equity risk rather than a direct measure of Canadian sentiment.",
    ),
    "credit": (
        "Credit demand",
        "Canadian investment-grade corporate OAS",
        "Canadian investment-grade corporate option-adjusted spreads measure the extra yield over the reference government curve after adjusting for embedded options. Investors generally demand a larger premium when they are less comfortable bearing credit and liquidity risk. Wider spreads therefore lower the greed score; narrower spreads raise it.\n\nSpreads also respond to issuer fundamentals, bond supply and liquidity. This is an investment-grade Canadian measure, not CNN's US high-yield indicator. It adds a bond-market perspective, but should not be interpreted as a pure measure of emotion.",
    ),
    "safe_haven": (
        "Safe-haven demand",
        "20-session stock minus aggregate-bond total return",
        "We subtract the Canada Aggregate bond index's 20-session total return from the TSX Composite's 20-session total return. Equity outperformance is consistent with investors favoring growth and risk; bond outperformance is consistent with a more defensive environment. A larger stock-minus-bond return relative to recent history raises the greed score.\n\nTotal returns include distributions, making the comparison more meaningful than price changes alone. The bond benchmark includes corporate as well as government debt, and interest-rate changes can move bonds independently of sentiment. This is a relative-performance proxy, not a direct measurement of money flows.",
    ),
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
        prior = values[max(0, i - window) : i]
        prior = prior[np.isfinite(prior)]
        if np.isfinite(value) and len(prior) >= minimum:
            out[i] = (
                100
                * ((prior < value).sum() + 0.5 * (prior == value).sum())
                / len(prior)
            )
    return pd.Series(out, index=series.index)


def mask_stale(series, limit=10):
    """Only mask from the Nth identical quote onward, never retroactively."""
    runs = series.groupby(series.ne(series.shift()).cumsum()).cumcount() + 1
    return series.mask(runs >= limit)


def aggregate(scores, minimum=5):
    count = scores.notna().sum(axis=1)
    valid = count >= minimum
    weights = (
        scores.notna().div(count.replace(0, np.nan), axis=0).where(valid, 0).fillna(0)
    )
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
    signals["momentum"] = (
        price / price.shift(1).rolling(125, min_periods=125).mean() - 1
    )
    signals["strength"] = (
        (get("tsx_52week_highs") - get("tsx_52week_lows"))
        .rolling(20, min_periods=20)
        .mean()
    )
    adv, dec = get("tsx_advancing"), get("tsx_declining")
    signals["breadth"] = (
        ((adv - dec) / (adv + dec).replace(0, np.nan))
        .rolling(20, min_periods=20)
        .mean()
    )
    if not config["breadth_enabled"]:
        signals["breadth"] = np.nan
    signals["options"] = get("mx_equity_put_call").rolling(5, min_periods=5).mean()
    signals["credit"] = get("canada_ig_credit_spread")
    signals["safe_haven"] = get("tsx_total_return").pct_change(
        20, fill_method=None
    ) - get("canada_bond_total_return").pct_change(20, fill_method=None)

    def rank(s):
        return past_percentile(s, config["rank_window"], config["rank_min_history"])

    scores = pd.DataFrame({c: rank(signals[c]) for c in signals}, index=data.index)
    for c in ("options", "credit"):
        scores[c] = 100 - scores[c]
    # Carry the last calculated score, not fabricated raw observations.
    options_date = pd.Series(data.index, index=data.index).where(scores["options"].notna()).ffill()
    scores["options"] = scores["options"].ffill()
    # Never percentile-rank a splice of differently defined volatility levels.
    source = pd.Series("Unavailable", index=data.index)
    vol_score = pd.Series(np.nan, index=data.index)
    vol_level = pd.Series(np.nan, index=data.index)
    # Increasing priority: US fallback, legacy Canadian, replacement Canadian.
    for name, label in [
        ("fred_vix", "US VIX fallback"),
        ("canada_vixc_history", "VIXC"),
        ("canada_vixi_history", "VIXI"),
    ]:
        series = mask_stale(get(name))
        if label == "VIXI":
            series = series.where(data.index >= "2021-04-26")
        elif label == "VIXC":
            series = series.where(data.index <= "2020-01-22")
        score = 100 - rank(series)
        use = score.notna()
        vol_score.loc[use], vol_level.loc[use], source.loc[use] = (
            score[use],
            series[use],
            label,
        )
    signals["volatility"] = vol_level
    scores["volatility"] = vol_score
    signals, scores = signals[list(COMPONENTS)], scores[list(COMPONENTS)]
    index, weights, count = aggregate(scores, config["minimum_components"])
    history = pd.DataFrame(
        {
            "index": index,
            "regime": index.map(regime),
            "active_components": count,
            "options_score_date": options_date,
            "options_carried_forward": options_date.notna() & options_date.ne(pd.Series(data.index, index=data.index)),
            "volatility_source": source,
            "tsx_price": price,
            "tsx_total_return": get("tsx_total_return"),
            "bond_total_return": get("canada_bond_total_return"),
            "vix_score": 100 - rank(mask_stale(get("fred_vix"))),
        }
    )
    keep = data.index >= config["display_start"]
    return IndexResult(
        history.loc[keep],
        signals.loc[keep],
        scores.loc[keep],
        weights.loc[keep],
        data.loc[keep],
    )
