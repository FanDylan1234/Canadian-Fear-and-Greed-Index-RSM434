"""Dashboard views for the frozen evaluation and its execution ledger."""

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from .chartsdesign import DATA_LINE, history_chart, style
from .dashboard_components import table
from .holdout import ALLOCATION, BENCHMARK_EQUITY, HORIZONS, SWITCH_COST


# Fifths of the 2010-2019 index scores, from most fearful to greediest.
GROUPS = ["Extreme fear", "Fear", "Neutral", "Greed", "Extreme greed"]
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


def calibration_details(r):
    models = r.calibration["models"]
    return html.Details([
        html.Summary("Frozen design and quintile boundaries"),
        html.P("The seven-indicator baseline ranks each signal against up to 252 prior TSX sessions, "
               "with 126 valid observations required. The index equally weights the available scores "
               "and requires at least five. The same rules apply throughout the holdout."),
        html.P(f"Boundaries use daily scores from {r.calibration['training_first']} through "
               "2019-12-31. A score on a boundary stays in the lower quintile. "
               "The Extreme fear group is the most fearful fifth of the training sample and Extreme greed the "
               "greediest. Holdout groups can differ in size."),
        table(["Signal", "Training scores", "20th percentile", "40th", "60th", "80th"],
              [[label, f"{models[key]['score_count']:,}", *[f"{cut:.4f}" for cut in models[key]["cuts"]]]
               for key, label in (("index", "Canadian index"), ("vix_score", "US VIX score"))],
              numeric_columns=(1, 2, 3, 4, 5)),
        html.P("The research design was reconstructed retrospectively from cached history. "
               "Historical revisions and the actual release time of a daily input can affect a replay."),
        download("Download full-precision calibration", "calibration.json"),
    ], className="quote-details")


def prediction(r):
    summary = r.prediction.set_index(["quintile", "months"])
    fig = go.Figure()
    labels = GROUPS
    cuts = r.calibration["models"]["index"]["cuts"]
    bounds = [0, *cuts, 100]
    ranges = [f"{lo:.1f}–{hi:.1f}" for lo, hi in zip(bounds, bounds[1:])]
    for (months, _), color in zip(HORIZONS.items(), ["#84243a", "#cb6b72", "#677a96"]):
        values = summary.xs(months, level="months").mean_return
        fig.add_bar(x=labels, y=values, name=f"{months} month" + ("s" if months > 1 else ""),
                    marker_color=color, hovertemplate="%{y:.2%}<extra>%{fullData.name}</extra>")
    style(fig, 320)
    fig.update_yaxes(title="Average total return", tickformat=".0%")
    rows = []
    for q, label in enumerate(labels, 1):
        cells = []
        for months in HORIZONS:
            s = summary.loc[(q, months)]
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
    low, high = summary.loc[(1, 1)], summary.loc[(5, 1)]
    if low.n and high.n:
        narrative = html.P(["After the most fearful readings, the TSX averaged ", html.Strong(pct(low.mean_return)),
                            f" over the next month, with {pct(low.mean_vol)} annualized volatility. "
                            "After the greediest readings, those figures were ", html.Strong(pct(high.mean_return)),
                            f" and {pct(high.mean_vol)}."], className="research-finding")
    return [html.H2("What followed each sentiment group?"), narrative, graph("prediction-returns", fig),
            results, html.P("Each group is one fifth of the index scores from 2010 to 2019, so its score range "
                            "differs slightly from the regime thresholds on the overview gauge. "
                            "One, three and six months correspond to 21, 63 and 126 observed TSX sessions. "
                            "Return includes reinvested dividends. Volatility is the sample standard deviation "
                            "of the following daily total returns, annualized using 252 sessions. Days counts "
                            "scored starting dates with a complete forward window. Adjacent windows overlap.",
                            className="muted"), calibration_details(r),
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
    wins = int((valid.advantage > 0).sum())
    ties = int((valid.advantage == 0).sum())
    if len(valid):
        losses = len(valid) - wins - ties
        finding = (f"Across {len(valid)} tests, US VIX had lower root mean squared error (RMSE) in {losses}, "
                   f"the Canadian index in {wins}, with {ties} ties.")
    else:
        finding = "No paired forecasts have matured."
    rows = [[f"{x.months}m", "TSX total return" if x.target == "return" else "Annualized volatility",
             f"{x.n:,}", pct(x.index_rmse), pct(x.vix_rmse),
             f"{100*x.advantage:+.3f} pp" if pd.notna(x.advantage) else "—"]
            for x in r.comparison.itertuples()]
    one_month = valid[(valid.months == 1) & (valid.target == "return")]
    example = None
    if not one_month.empty:
        m = one_month.iloc[0]
        example = html.P(f"For one-month returns, the Canadian forecast was closer on "
                         f"{int(m.index_closer_days):,} of {int(m.n):,} dates. Across all those dates, "
                         f"its RMSE was {pct(m.index_rmse)} and US VIX’s was {pct(m.vix_rmse)}. "
                         f"The gap was {abs(m.advantage)*100:.3f} percentage points.")
    return [html.H2("Does the Canadian index beat US VIX alone?"), html.P(finding, className="research-finding"),
            html.P("Each test compares errors across many dates for one outcome and horizon. "
                   "The six tests cover returns and volatility over one, three and six months. "
                   "A signal can win a test even when the other signal is closer on many individual days."),
            table(["Horizon", "Forecast target", "Dates compared", "Index RMSE", "VIX RMSE", "Index advantage"],
                  rows, numeric_columns=(2, 3, 4, 5)),
            example,
            html.P("Each signal forecasts the historical mean outcome for its own quintile. Both sets of "
                   "means use the same training dates and only outcomes completed by December 31, 2019. "
                   "US VIX uses its own inverted trailing percentile, so high implied volatility ranks as fear."),
            html.P("Dates compared counts the holdout dates on which both signals produced a forecast and "
                   "the outcome had fully played out. Both errors are measured on exactly these dates, so "
                   "neither signal is scored on a date the other lacks. Longer horizons have fewer dates "
                   "because the final months of the holdout have not yet matured."),
            html.P("Root mean squared error (RMSE) measures the typical size of a forecast miss and gives "
                   "larger misses more weight. Both forecasts face exactly the same holdout dates for each "
                   "target. Positive advantage means the Canadian index reduced RMSE, in percentage points."),
            html.P("The Canadian index uses no US VIX data. When no Canadian volatility score is "
                   "available, its other indicators share the weight. Overlapping forecast windows "
                   "limit the interpretation of small differences.", className="muted"),
            calibration_details(r), download("Download matched forecast errors (CSV)", "vix-comparison.csv")]


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
                                 "quintiles, realized outcomes, forecasts, the trade ledger and source-file hashes. "
                                 "Join the files on date. Returns and volatility in the CSVs are decimals."),
                          html.P("The current training data match the frozen calibration fingerprint."
                                 if manifest["holdout"]["training_matches_freeze"] else
                                 "The local training history differs from the frozen snapshot. "
                                 "Forecasts continue to use the saved calibration."),
                          html.P([html.A("Bloomberg Canada Aggregate factsheet",
                                         href="https://assets.bbhub.io/professional/sites/27/Canada-Aggregate-Index.pdf"),
                                  " · ", html.A("Cboe daily VIX history",
                                               href="https://www.cboe.com/tradable_products/vix/vix_historical_data/")])],
                         className="quote-details"),
            html.Div(download("Download complete audit bundle (ZIP)", "holdout-audit.zip"),
                     className="download-links")]
