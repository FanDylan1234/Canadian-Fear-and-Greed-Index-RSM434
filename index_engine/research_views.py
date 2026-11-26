"""Dashboard views for sentiment-based forecasts and their evaluation."""

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from .chartsdesign import DATA_LINE, history_chart, style
from .dashboard_components import table
from .buildindicatorsfromdata import SENTIMENT_RANGES
from .holdout import ALLOCATION, BENCHMARK_EQUITY, HORIZONS, SWITCH_COST


# Methodology score bands, from fear to greed.
GROUPS = list(SENTIMENT_RANGES)
# Fear in reds through greed in blues, matching the overview gauge.
GROUP_COLORS = ["#84243a", "#cb6b72", "#b5a9a4", "#7f95b5", "#3f5a80"]
SERIES_COLORS = {"strategy": DATA_LINE, "benchmark": "#b3123a", "equity": "#4f6f9c"}

TABS = {"prediction": "Prediction", "episodes": "Episodes",
        "vix": "US VIX comparison", "backtest": "Backtest"}


def pct(x):
    return f"{x:.2%}" if pd.notna(x) else "—"


def day(x):
    return f"{x:%b %d, %Y}" if pd.notna(x) else "—"


def graph(name, fig):
    # Give Dash a real container height even when the tab first mounts while hidden.
    return dcc.Graph(id=name, figure=fig, responsive=True,
                     style={"height": f"{fig.layout.height}px", "width": "100%"},
                     config={"displaylogo": False})


def download(label, filename):
    return html.A(label, href="/download/" + filename, className="text-link")


def return_pattern(r):
    rows = []
    for months in HORIZONS:
        groups = r.prediction[r.prediction.months == months].set_index("sentiment").reindex(GROUPS)
        values = groups.mean_return
        if values.isna().any():
            finding = "Not enough completed outcomes in every group"
        elif (values.diff().dropna() < 0).all():
            finding = "Yes — average returns fall at every step from fear to greed"
        else:
            finding = "Mixed — average returns do not fall at every step from fear to greed"
        rows.append([f"{months} month" + ("s" if months > 1 else ""), finding])
    return table(["Horizon", "Does more fear consistently precede a higher return?"], rows)


def prediction(r):
    summary = r.prediction.set_index(["sentiment", "months"])
    fig = go.Figure()
    labels = GROUPS
    ranges = list(SENTIMENT_RANGES.values())
    # Horizons on the axis, one bar per sentiment group within each horizon.
    horizons = [f"{m} month" + ("s" if m > 1 else "") for m in HORIZONS]
    for label, color in zip(labels, GROUP_COLORS):
        values = summary.xs(label, level="sentiment").mean_return.reindex(list(HORIZONS))
        fig.add_bar(x=horizons, y=values, name=label, marker_color=color,
                    hovertemplate="%{y:.2%}<extra>%{fullData.name}</extra>")
    style(fig, 320)
    fig.update_layout(barmode="group", bargroupgap=0.08)
    fig.update_yaxes(title="Average total return", tickformat=".0%")
    rows = []
    for q, label in enumerate(labels, 1):
        cells = []
        for months in HORIZONS:
            s = summary.loc[(label, months)]
            cells.extend([pct(s.mean_return), pct(s.mean_vol), f"{int(s.n):,}"])
        rows.append([label, ranges[q - 1], *cells])
    # Grouped headers keep the return, volatility and denominator for each horizon together.
    headers = html.Thead([
        html.Tr([html.Th("Index group", rowSpan=2, scope="col"), html.Th("Score range", rowSpan=2, scope="col"),
                 *[html.Th(f"{m} month" + ("s" if m > 1 else ""), colSpan=3, scope="colgroup") for m in HORIZONS]]),
        html.Tr([html.Th(s, scope="col") for _ in HORIZONS for s in ["Return", "Ann. vol.", "Days"]]),
    ])
    results = html.Div(html.Table([headers, html.Tbody([html.Tr([html.Td(c) for c in row]) for row in rows])]),
                       className="table-scroll research-grid")
    narrative = None
    low, high = summary.loc[("Extreme fear", 1)], summary.loc[("Extreme greed", 1)]
    if low.n and high.n:
        narrative = html.P(["After Extreme fear (below 25), the TSX averaged ", html.Strong(pct(low.mean_return)),
                            f" over the next month, with {pct(low.mean_vol)} annualized volatility. "
                            "After Extreme greed (above 75), those figures were ", html.Strong(pct(high.mean_return)),
                            f" and {pct(high.mean_vol)}."], className="research-finding")
    return [html.H2("Does fear precede stronger TSX returns?"),
            html.P("The hypothesis is contrarian: Extreme fear should be followed by the highest average "
                   "return, then Fear, Neutral, Greed and Extreme greed. We test that expectation against "
                   "what actually happened from 2020 onward; the results are allowed to disagree."),
            narrative, graph("prediction-returns", fig), results, return_pattern(r),
            html.P("Groups use the same score bands as Methodology and the Overview gauge. Decimal "
                   "scores are classified before rounding; 24.9 is Extreme fear and 25.0 is Fear. "
                   "Groups can have very different numbers of days."),
            html.P("These are observed outcomes, not forecasts made in advance. One, three and six "
                   "months mean 21, 63 and 126 TSX sessions. Return includes reinvested dividends. "
                   "Annualized volatility measures how much daily returns fluctuated during that window. "
                   "Days counts starting dates with a complete outcome; overlapping windows are not "
                   "independent examples. Small groups are less reliable.", className="muted"),
            html.P("The US VIX comparison tab asks a separate question: using only pre-2020 examples "
                   "to make forecasts, which signal was closer to the actual TSX outcomes after 2019?"),
            download("Download daily scores and forward outcomes (CSV)", "observations.csv")]


def episodes(r):
    rows, charts = [], []
    for i, e in enumerate(r.episodes.itertuples()):
        window = r.audit.loc[e.start:e.end]
        finding = "Yes" if e.fear_days else ("No observed breach" if e.scored else "No scores")
        rows.append([e.episode, finding, f"{e.fear_days} / {e.scored}", e.sessions - e.scored,
                     day(e.first_fear), f"{e.low:.2f}" if e.scored else "—", day(e.low_date)])
        if e.scored:
            fig = history_chart(window)
            fig.update_layout(height=280, showlegend=False)
            fig.add_hline(y=25, line_dash="dot", line_color="#8d3742")
            charts.append(html.Div([html.H3(e.episode), graph(f"episode-{i}", fig)]))
    return [html.H2("Did the index register extreme fear?"),
            html.P("A daily score below 25 qualifies as extreme fear. Each window includes every observed "
                   "TSX session in the named month or year. The dotted line marks the threshold."),
            table(["Episode", "Extreme fear?", "Fear days / scored days", "Unscored days", "First fear",
                   "Lowest score", "First date at low"], rows, numeric_columns=(2, 3, 5)),
            html.Div(charts, className="episode-charts"),
            download("Download episode results (CSV)", "episodes.csv")]


def vix_comparison(r):
    valid = r.comparison.dropna(subset=["advantage"])
    rows = []
    for x in r.comparison.itertuples():
        winner = ("Canadian index" if x.advantage > 0 else "US VIX" if x.advantage < 0 else
                  "Tie" if pd.notna(x.advantage) else "No paired forecasts")
        rows.append([f"{x.months}m", "TSX total return" if x.target == "return" else "Annualized TSX volatility",
                     f"{x.n:,}", f"{100*x.index_rmse:.3f} pp" if pd.notna(x.index_rmse) else "—",
                     f"{100*x.vix_rmse:.3f} pp" if pd.notna(x.vix_rmse) else "—", winner])
    findings = []
    for target, label in (("return", "return"), ("vol", "volatility")):
        tests = valid[valid.target == target]
        if len(tests):
            wins = int((tests.advantage > 0).sum())
            losses = int((tests.advantage < 0).sum())
            findings.append(f"For {label} forecasts, the Canadian index had the smaller error at "
                            f"{wins} of {len(tests)} horizons; US VIX won {losses}, with "
                            f"{len(tests) - wins - losses} ties.")
    if not findings:
        findings = ["No dates yet have a completed outcome and both forecasts."]
    summary = r.prediction.set_index(["sentiment", "months"])
    fear, greed = summary.loc[("Extreme fear", 1)], summary.loc[("Extreme greed", 1)]
    observed = None
    if fear.n and greed.n:
        observed = html.P(f"In Prediction, the observed one-month return after Extreme fear is "
                          f"{pct(fear.mean_return)}, versus {pct(greed.mean_return)} after Extreme greed. "
                          "Those averages describe 2020 onward. Here we test forecasts learned from "
                          "2010–2019, so future outcomes cannot teach the model its own answers.")
    example = None
    cols = ["return_1m", "index_forecast_return_1m", "vix_score_forecast_return_1m"]
    paired = r.audit.loc[r.audit.period == "holdout"].dropna(subset=cols)
    if len(paired):
        sample = paired.iloc[-1]
        index_error = abs(sample.index_forecast_return_1m - sample.return_1m) * 100
        vix_error = abs(sample.vix_score_forecast_return_1m - sample.return_1m) * 100
        example = html.P(f"One completed example: on {day(paired.index[-1])}, the Canadian index was "
                         f"{sample.index_sentiment} and forecast {pct(sample.index_forecast_return_1m)} "
                         f"over the next month. US VIX was {sample.vix_score_sentiment} and forecast "
                         f"{pct(sample.vix_score_forecast_return_1m)}. The TSX actually returned "
                         f"{pct(sample.return_1m)} by {day(sample.end_1m)}. The misses were "
                         f"{index_error:.2f} and {vix_error:.2f} percentage points, respectively.",
                         className="research-finding")
    return [html.H2("Which sentiment signal forecasts the TSX better?"),
            html.P("We compare two ways to forecast the same future TSX return and volatility: the "
                   "Canadian Fear & Greed Index and US VIX alone. We are not forecasting the future "
                   "VIX level or comparing Canadian returns with US stock returns."),
            *[html.P(finding, className="research-finding") for finding in findings],
            observed,
            html.H3("From today's sentiment to a forecast"),
            html.Ol([
                html.Li("Read the sentiment score. Both signals use the Methodology bands: below 25 "
                        "is Extreme fear, 25 to below 45 is Fear, 45–55 is Neutral, above 55–75 is Greed, "
                        "and above 75 is Extreme greed."),
                html.Li("Look up what followed that sentiment in 2010–2019. That group's average TSX "
                        "return is the return forecast; its average future volatility is the volatility "
                        "forecast. Each signal uses its own group averages, learned on the same eligible dates."),
                html.Li("For each date from 2020 onward, compare those forecasts with what happened "
                        "over the following 1, 3 or 6 months. Score both on exactly the same dates.")]),
            html.P("The hypothesis from Prediction is that more fear precedes stronger returns. "
                   "We do not force the forecasts into that order: they follow the training evidence. "
                   "High US VIX means more expected turbulence. Its score reverses its rank against "
                   "prior observations, so unusually high VIX maps toward fear. A score of 25 here "
                   "does not mean a raw VIX level of 25."),
            html.H3("Which was closer after 2019?"),
            html.P("Smaller forecast error is better. Errors below use percentage points (pp); "
                   "RMSE is explained with an example just below the table."),
            table(["Horizon", "What is forecast", "Dates compared", "Canadian error (RMSE)",
                   "US VIX error (RMSE)", "Smaller error"], rows, numeric_columns=(2, 3, 4)),
            html.H3("Reading the error: smaller is better"),
            html.P("RMSE stands for root mean squared error. For each date, subtract the actual "
                   "outcome from the forecast, square the miss, average all squared misses, then take "
                   "the square root. It summarizes forecast misses and penalizes large misses more."),
            html.P("For example, a +5% return forecast followed by a +2% return misses by 3 percentage "
                   "points. If every miss were that size, RMSE would be 3 pp. An RMSE of 3 pp is "
                   "better than 4 pp. It is not a return earned, a success rate, or an error in the "
                   "0–100 sentiment score. Volatility errors also use percentage points."),
            example,
            html.P("Dates compared includes only completed outcomes with both forecasts. A group with "
                   "no training examples supplies no forecast; it is never assigned a zero return. "
                   "Longer horizons lose the most recent, unfinished windows. Return and volatility "
                   "are separate tests: winning one does not mean winning the other. Lower RMSE "
                   "does not necessarily mean being closer on more days or earning a better portfolio return."),
            html.P("This is a retrospective comparison. Historical revisions can change training "
                   "averages, and overlapping windows limit what small differences establish. The "
                   "Canadian index contains no US VIX data. Use Backtest for portfolio performance.",
                   className="muted"),
            download("Download matched forecast errors (CSV)", "vix-comparison.csv")]


def backtest(r):
    ledger = r.ledger
    if len(ledger) < 2:
        return [html.H2("Sentiment allocation versus 60/40"),
                html.P("At least two holdout closes with both total-return levels are needed.")]
    perf = r.performance.set_index("portfolio")
    ours, base = perf.loc["Sentiment strategy"], perf.loc["60/40 strategy"]
    bench = f"{BENCHMARK_EQUITY:.0%}/{1 - BENCHMARK_EQUITY:.0%}".replace("%", "")

    def pp(x):
        return f"{100 * x:+.2f} pp"

    summary = [
        ["Ending value of CAD 100", f"CAD {ours.end_wealth:,.2f}", f"CAD {base.end_wealth:,.2f}",
         f"CAD {ours.end_wealth - base.end_wealth:+,.2f}"],
        ["Cumulative return", pct(ours.total_return), pct(base.total_return),
         pp(ours.total_return - base.total_return)],
        ["Annualized return", pct(ours.cagr), pct(base.cagr), pp(ours.cagr - base.cagr)],
        ["Annualized volatility", pct(ours.volatility), pct(base.volatility),
         pp(ours.volatility - base.volatility)],
        ["Sharpe ratio", f"{ours.sharpe:.2f}", f"{base.sharpe:.2f}", f"{ours.sharpe - base.sharpe:+.2f}"],
        ["Maximum drawdown", pct(ours.max_drawdown), pct(base.max_drawdown),
         pp(ours.max_drawdown - base.max_drawdown)],
    ]
    references = [[name, f"CAD {x.end_wealth:,.2f}", pct(x.total_return), pct(x.cagr), pct(x.volatility),
                   f"{x.sharpe:.2f}", pct(x.max_drawdown)]
                  for name, x in perf.drop(["Sentiment strategy", "60/40 strategy"]).iterrows()]
    held = ledger.signal_regime.value_counts()
    composition = [[g, f"{ALLOCATION[g]:.0%}", f"{1 - ALLOCATION[g]:.0%}", f"{int(held.get(g, 0)):,}"]
                   for g in GROUPS]
    trades = ledger[ledger.switched]
    fig = go.Figure()
    for col, name, key in [("strategy_wealth", "Sentiment strategy", "strategy"),
                           ("benchmark_wealth", f"{bench} strategy", "benchmark"),
                           ("equity_wealth", "TSX buy and hold", "equity")]:
        fig.add_scatter(x=ledger.index, y=ledger[col], name=name, mode="lines",
                        line=dict(color=SERIES_COLORS[key], width=2.4 if key == "strategy" else 1.8),
                        hovertemplate="CAD %{y:.2f}<extra>%{fullData.name}</extra>")
    style(fig, 340)
    fig.update_yaxes(title="Value of CAD 100")
    verdict = "higher" if ours.sharpe > base.sharpe else "lower" if ours.sharpe < base.sharpe else "the same"
    return [html.H2(f"Sentiment allocation versus a {bench} portfolio"),
            html.P(f"Both portfolios start with CAD 100 split {bench} between TSX equities and Canadian "
                   "aggregate bonds. The sentiment strategy holds 100% equities after an Extreme fear reading, "
                   f"100% bonds after an Extreme greed reading, and {bench} otherwise. The benchmark always "
                   f"holds {bench}. A missing score keeps the last allocation."),
            html.P([f"From {day(ledger.index[0])} to {day(ledger.index[-1])}, the sentiment strategy returned ",
                    html.Strong(pct(ours.total_return)), f" against {pct(base.total_return)} for {bench}, with "
                    f"{pct(ours.volatility)} annualized volatility against {pct(base.volatility)}. Its Sharpe "
                    f"ratio was {verdict}: ", html.Strong(f"{ours.sharpe:.2f}"),
                    f" against {base.sharpe:.2f}."], className="research-finding"),
            graph("backtest-wealth", fig),
            html.H3("Performance summary"),
            table(["Measure", "Sentiment strategy", f"{bench} strategy", "Difference"], summary,
                  numeric_columns=(1, 2, 3)),
            html.H3("Sentiment strategy allocation"),
            table(["Regime at the signal close", "Equities", "Bonds", "Holdout sessions in force"], composition,
                  numeric_columns=(1, 2, 3)),
            html.P("Regimes use the overview thresholds: Extreme fear is below 25 and Extreme greed is above 75. "
                   "Each session counts the regime whose allocation applied after that close.", className="muted"),
            html.H3("Execution and limits"),
            html.P("Each signal can execute at the next close with both asset levels. The prior mix earns "
                   "the return up to that close. Both portfolios rebalance to their target mix at every such "
                   f"close. Trading costs {SWITCH_COST:.2%} of the value moved between equities and bonds, "
                   f"so a full switch costs {SWITCH_COST:.2%} of the portfolio. There were "
                   f"{len(r.audit[r.audit.period == 'holdout']) - len(ledger)} holdout sessions without both "
                   "asset levels. Positions carry across those gaps."),
            html.P("Annualized volatility is the standard deviation of daily returns times the square root of "
                   "252. The Sharpe ratio is the annualized mean daily return divided by that volatility. It "
                   "uses a 0% risk-free rate because no cash-rate series is loaded. A positive cash rate lowers "
                   "both ratios, and lowers the less volatile portfolio's ratio by more."),
            html.P("Extreme readings can persist. Moving to bonds can miss an equity rally, and bonds can "
                   "fall when yields rise. Both legs use benchmark total returns. An ETF investor would also "
                   "face fund fees, tracking differences, taxes and variable trading costs. Historical "
                   "releases may have arrived later than the assumed trade time."),
            html.Details([html.Summary("Single-asset and before-cost references"),
                          table(["Portfolio", "Ending CAD", "Total return", "Annualized return",
                                 "Annualized volatility", "Sharpe ratio", "Max. drawdown"],
                                references, numeric_columns=(1, 2, 3, 4, 5, 6))], className="quote-details"),
            html.Details([html.Summary(f"Inspect the {len(trades)} allocation changes"),
                          table(["Signal close", "Score", "Regime", "Execution close", "New equity weight",
                                 "Wealth after cost"],
                                [[day(x.signal_date), f"{x.signal_score:.2f}", x.signal_regime, day(date),
                                  f"{x.equity_after_close:.0%}", f"CAD {x.strategy_wealth:.2f}"]
                                 for date, x in trades.iterrows()],
                                numeric_columns=(1, 4, 5))], className="quote-details"),
            download("Download the dated backtest ledger (CSV)", "backtest-ledger.csv")]


def research_page(view, r, manifest):
    if r is None:
        return [html.H2(TABS[view]), html.P("Rebuild the daily history to calculate this analysis.")]
    hold = r.audit[r.audit.period == "holdout"]
    if hold.empty:
        return [html.H2(TABS[view]), html.P("The loaded history ends before the 2020 holdout.")]
    pages = {"prediction": prediction, "episodes": episodes, "vix": vix_comparison, "backtest": backtest}
    sources = [row for row in manifest["coverage"] if row["dataset"] in {
        "tsx_total_return", "canada_bond_total_return", "fred_vix"}]
    source_rows = [[s["dataset"] + ".csv", s["security"], s["field"], s["last"], s["status"]] for s in sources]
    basis_warning = next((s["status"] for s in sources if s.get("basis_break_date")), None)
    return [html.P(f"Holdout · {day(hold.index[0])} – {day(hold.index[-1])}", className="research-period"),
            html.P(f"TSX total-return data: {basis_warning}. Refresh data to reload the fixed-start history.",
                   role="status") if basis_warning else None,
            *pages[view](r),
            html.Details([html.Summary("Trace the data and reproduce the results"),
                          table(["Local source file", "Instrument / distributor", "Field", "Last source date",
                                 "Status"], source_rows),
                          html.P("The audit bundle includes dated source levels, component scores and weights, "
                                 "sentiment groups, realized outcomes, forecasts, the trade ledger and source-file hashes. "
                                 "Join the files on date. Returns and volatility in the CSVs are decimals."),
                          html.P("Forecast averages use only outcomes completed by December 31, 2019. "
                                 "Each rebuild records its training fingerprint and exact group means "
                                 "in calibration.json. Changes to historical inputs can change these means."),
                          html.P([html.A("Bloomberg Canada Aggregate factsheet",
                                         href="https://assets.bbhub.io/professional/sites/27/Canada-Aggregate-Index.pdf"),
                                  " · ", html.A("Cboe daily VIX history",
                                               href="https://www.cboe.com/tradable_products/vix/vix_historical_data/")])],
                         className="quote-details"),
            html.Div(download("Download complete audit bundle (ZIP)", "holdout-audit.zip"),
                     className="download-links")]
