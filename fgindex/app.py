"""Dashboard pages, user controls, and downloadable reports."""

import argparse
import datetime as dt
from zoneinfo import ZoneInfo
import pandas as pd
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from flask import abort, send_file
from fgindex.data import ROOT
from fgindex.model import COMPONENTS, regime
from fgindex.charts import gauge, history_chart, signal_chart, weights_chart, color
from fgindex.service import DashboardService

GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}


def table(headers, rows):
    return html.Div(
        html.Table(
            [
                html.Thead(html.Tr([html.Th(h) for h in headers])),
                html.Tbody([html.Tr([html.Td(c) for c in row]) for row in rows]),
            ]
        ),
        className="table-scroll",
    )


def score_badge(value):
    return html.Span(
        regime(value), className="badge", style={"backgroundColor": color(value)}
    )


def comparison(history):
    date = history.index[-1]
    rows = []
    for label, target in [
        ("Previous close", date - pd.Timedelta(days=1)),
        ("1 week ago", date - pd.Timedelta(days=7)),
        ("1 month ago", date - pd.DateOffset(months=1)),
        ("1 year ago", date - pd.DateOffset(years=1)),
    ]:
        past = history.loc[:target]
        if len(past) and (target - past.index[-1]).days <= 7:
            value = past["index"].iloc[-1]
            dated = str(past.index[-1].date())
        else:
            value, dated = float("nan"), "No observation"
        rows.append(
            html.Div(
                [
                    html.Div(
                        [html.Strong(label), html.Small(dated), html.Div(regime(value))]
                    ),
                    html.Span(
                        f"{value:.0f}" if pd.notna(value) else "—",
                        className="round-score",
                        style={"backgroundColor": color(value)},
                    ),
                ],
                className="comparison-row",
            )
        )
    return html.Div(rows, className="comparisons")


def overview(result):
    history = result.history
    latest = history.iloc[-1]
    cards = []
    for number, (key, (title, subtitle, rationale)) in enumerate(COMPONENTS.items(), 1):
        value = result.scores[key].iloc[-1]
        weight = result.weights[key].iloc[-1]
        cards.append(
            html.Article(
                [
                    html.Div(
                        [
                            html.Span(f"0{number}", className="indicator-number"),
                            html.Div([html.H3(title), html.P(subtitle)]),
                            score_badge(value),
                        ],
                        className="indicator-heading",
                    ),
                    html.Div(
                        [
                            dcc.Graph(
                                figure=signal_chart(result, key), config=GRAPH_CONFIG
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Strong(
                                                f"{value:.1f}"
                                                if pd.notna(value)
                                                else "—"
                                            ),
                                            html.Span(" / 100"),
                                        ],
                                        className="component-score",
                                    ),
                                    html.P(rationale),
                                    html.P(
                                        f"Current index weight: {weight:.2%}",
                                        className="weight-label",
                                    ),
                                    html.Small(
                                        "Unavailable or warming up: excluded and reweighted."
                                        if pd.isna(value)
                                        else "Percentile uses only prior observations."
                                    ),
                                ],
                                className="indicator-explanation",
                            ),
                        ],
                        className="indicator-body",
                    ),
                ],
                className="indicator",
            )
        )
    return [
        html.Div(
            [
                html.Div(
                    [
                        dcc.Graph(figure=gauge(latest["index"]), config=GRAPH_CONFIG),
                        html.P(
                            f"Daily observation · {history.index[-1]:%b %d, %Y}",
                            className="chart-caption",
                        ),
                    ]
                ),
                comparison(history),
            ],
            className="overview-grid",
        ),
        html.Div(
            [
                html.H2("The indicators behind the index"),
                html.Span(
                    f"{int(latest.active_components)} of 7 available", className="pill"
                ),
            ],
            className="section-heading",
        ),
        html.P(
            "Every available indicator has the same weight. Select Timeline to explore past readings and changing coverage.",
            className="muted",
        ),
        *cards,
    ]


def timeline(result, start, end):
    frame = result.history.loc[start:end]
    valid = frame["index"].dropna()
    stats = [
        ("Lowest reading", f"{valid.min():.1f}" if len(valid) else "—"),
        ("Highest reading", f"{valid.max():.1f}" if len(valid) else "—"),
        ("Average reading", f"{valid.mean():.1f}" if len(valid) else "—"),
        ("Sessions with a score", f"{len(valid):,}"),
    ]
    return [
        html.Div(
            [
                html.H2("A history of Canadian market sentiment"),
                html.A(
                    "Download history ↓",
                    href="/download/history.csv",
                    className="text-link",
                ),
            ],
            className="section-heading",
        ),
        html.P(
            "Historical index readings from 2010. Hover to inspect the score, available components and volatility source. Gaps remain visible.",
            className="muted",
        ),
        dcc.Graph(
            figure=history_chart(result.history, start, end),
            config={"displaylogo": False, "scrollZoom": False},
        ),
        html.Div(
            [
                html.Div([html.Small(label), html.Strong(value)])
                for label, value in stats
            ],
            className="stats-grid",
        ),
        html.H3("How the weights changed"),
        html.P(
            "Missing inputs receive 0%; their allocation is divided equally across available components. A minimum of five is required.",
            className="muted",
        ),
        dcc.Graph(
            figure=weights_chart(result.weights.loc[start:end]), config=GRAPH_CONFIG
        ),
        html.H3("Read the history with its limits"),
        html.Ul(
            [
                html.Li(
                    "2010: options history is unavailable. Early dates may also need pre-2010 data to warm up the scoring windows."
                ),
                html.Li(
                    "Breadth uses verified TSX Composite data only. Legacy TSX Venture exports are excluded, including their apparent 2015 start."
                ),
                html.Li(
                    "Canadian volatility has a 2020–21 gap. US VIX is a labelled fallback during gaps, stale runs and Canadian-series warmup."
                ),
                html.Li(
                    "Changing component sets and volatility definitions affect comparability across time. This is a sentiment timeline, not trading returns."
                ),
            ],
            className="notes",
        ),
    ]


def coverage_view(result, manifest, selected_date):
    date = pd.Timestamp(selected_date) if selected_date else result.history.index[-1]
    dates = result.history.index[result.history.index <= date]
    selected = dates[-1] if len(dates) else None
    rows = []
    if selected is not None:
        for key, (label, _, _) in COMPONENTS.items():
            value = result.scores.loc[selected, key]
            rows.append(
                [
                    label,
                    f"{value:.2f}" if pd.notna(value) else "Unavailable",
                    f"{result.weights.loc[selected, key]:.2%}",
                ]
            )
    return [
        html.H2("Data coverage & allocations"),
        html.P(
            "Observed source dates are reported below. A successful numeric download does not, by itself, verify the series definition.",
            className="muted",
        ),
        table(
            ["Dataset", "Bloomberg mapping", "First observation", "Latest", "Status"],
            [
                [
                    r["dataset"],
                    r["security"] + " / " + r["field"],
                    r["first"] or "—",
                    r["last"] or "—",
                    r["status"] + (" · definition review" if r["review"] else ""),
                ]
                for r in manifest["coverage"]
            ],
        ),
        html.H3("Weights on your selected date"),
        html.P(
            f"Observation: {selected.date()}"
            if selected is not None
            else "No observation before that date."
        ),
        table(["Component", "Score", "Weight"], rows),
        html.Div(
            [
                html.A("Download weights ↓", href="/download/weights.csv"),
                html.A("Download coverage ↓", href="/download/coverage.csv"),
            ],
            className="download-links",
        ),
    ]


def methodology(config):
    return [
        html.H2("How the index works"),
        html.P(
            "A Canadian adaptation of the familiar fear-to-greed scale, with transparent inputs and reproducible daily history.",
            className="lead",
        ),
        html.H3("One scale. Equal weights."),
        html.P(
            f"Each indicator is ranked against its previous {config['rank_window']} TSX sessions, requiring at least {config['rank_min_history']} finite prior readings. Today's value is excluded from its comparison window. Ties receive the midpoint rank. Scores are inverted for put/call, volatility and credit spreads, so a higher score always means more greed."
        ),
        table(
            ["Score", "Reading"],
            [
                ["0–<25", "Extreme fear"],
                ["25–<45", "Fear"],
                ["45–55", "Neutral"],
                [">55–75", "Greed"],
                [">75–100", "Extreme greed"],
            ],
        ),
        html.P(
            "The index is the arithmetic mean of available scores. Seven available means 1/7 each; six means 1/6 each; five means 1/5 each. Fewer than five means no published score. No missing values are backfilled or carried forward."
        ),
        html.H3("Daily history and live quotes are separate"),
        html.P(
            "History uses observations dated no later than yesterday in Toronto. Bloomberg quotes are polled every minute and displayed with vendor timestamps. They never overwrite the completed daily index. Cached values remain available if Bloomberg disconnects, and their observation date stays visible."
        ),
        html.H3("Source and definition limits"),
        html.P(
            "Breadth and new highs/lows use TSX Composite constituents. Credit uses Canadian investment-grade corporate option-adjusted spreads, not US high-yield spreads. The bond comparison uses Canada Aggregate total return, which includes corporate bonds; it is not a pure government safe-haven benchmark."
        ),
        html.P(
            "VIXC and VIXI are ranked separately before their scores are selected. US VIX is used during missing Canadian history or Canadian warmup, and is labelled in every exported row. Identical volatility quotes are excluded from the tenth consecutive repeated observation onward; repeated zero breadth counts remain valid."
        ),
        html.H3("Research scope"),
        html.P(
            "This release reconstructs a historical sentiment timeline. It does not measure strategy P&L or claim predictive performance. The assignment's holdout prediction study, US VIX comparison and trading-rule exercise remain separate future deliverables."
        ),
        html.P(
            "Historical vendor data may be revised and are not a point-in-time vintage archive. The calculation is causal, but cannot establish that all source values were published at the same time. Session dates follow available TSX price observations rather than an independently certified exchange calendar."
        ),
        html.Div(
            [
                html.A(
                    "CNN design reference ↗",
                    href="https://www.cnn.com/markets/fear-and-greed",
                    target="_blank",
                ),
                html.A(
                    "Project repository ↗",
                    href="https://github.com/FanDylan1234/Canadian-Fear-and-Greed-Index-RSM434",
                    target="_blank",
                ),
            ],
            className="download-links",
        ),
    ]


def create_app(offline=False, start_worker=False, service=None):
    service = service or DashboardService(offline=offline)
    app = Dash(
        __name__,
        assets_folder=str(ROOT / "assets"),
        title="Canadian Fear & Greed Index",
        update_title=None,
    )
    app.service = service
    result, _, _, _, _, _ = service.snapshot()
    latest = (
        str(result.history.index[-1].date())
        if result is not None
        else dt.date.today().isoformat()
    )
    app.layout = html.Div(
        [
            html.Header(
                html.Div(
                    [
                        html.A(
                            [
                                html.Span("C", className="brand-mark"),
                                html.Strong("MARKET SENTIMENT"),
                                html.Span("CANADA", className="nav-country"),
                            ],
                            href="/",
                            className="brand",
                        ),
                        html.Span("RSM434 · ROTMAN COMMERCE", className="nav-project"),
                    ],
                    className="nav-inner",
                )
            ),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("CANADIAN MARKETS", className="eyebrow"),
                                    html.H1("Fear & Greed Index"),
                                    html.P(
                                        "What emotion is driving the Canadian market?",
                                        className="lead",
                                    ),
                                ]
                            ),
                            html.Button(
                                "↻ Refresh data",
                                id="refresh-button",
                                n_clicks=0,
                                className="refresh-button",
                            ),
                        ],
                        className="hero-heading",
                    ),
                    html.Div(id="status-banner", role="status"),
                    html.Div(id="quote-strip"),
                    dcc.Tabs(
                        id="view",
                        value="overview",
                        className="tabs",
                        children=[
                            dcc.Tab(
                                label=label,
                                value=value,
                                className="tab",
                                selected_className="tab-selected",
                            )
                            for label, value in [
                                ("Overview", "overview"),
                                ("Timeline", "timeline"),
                                ("Data & weights", "data"),
                                ("Methodology", "methodology"),
                            ]
                        ],
                    ),
                    html.Div(
                        [
                            html.Label("Timeline range"),
                            dcc.DatePickerRange(
                                id="date-range",
                                start_date="2010-01-01",
                                end_date=latest,
                                display_format="MMM D, YYYY",
                                min_date_allowed="2010-01-01",
                            ),
                            html.Label("Inspect weights"),
                            dcc.DatePickerSingle(
                                id="weight-date",
                                date=latest,
                                display_format="MMM D, YYYY",
                                min_date_allowed="2010-01-01",
                            ),
                        ],
                        id="date-controls",
                        className="date-controls",
                    ),
                    html.Div(id="page-content"),
                    html.Footer(
                        [
                            html.Strong("Canadian Fear & Greed Index"),
                            html.Span(
                                "Independent academic project · Bloomberg / Montréal Exchange / FRED"
                            ),
                            html.Small(
                                "Daily observations. Transparent coverage. No affiliation with CNN."
                            ),
                        ]
                    ),
                ],
                className="container",
            ),
            dcc.Interval(id="ui-tick", interval=5000, n_intervals=0),
        ]
    )

    @app.callback(
        Output("page-content", "children"),
        Output("status-banner", "children"),
        Output("quote-strip", "children"),
        Output("date-controls", "style"),
        Output("refresh-button", "disabled"),
        Input("view", "value"),
        Input("ui-tick", "n_intervals"),
        Input("refresh-button", "n_clicks"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("weight-date", "date"),
    )
    def render(view, tick, clicks, start, end, selected_date):
        if ctx.triggered_id == "refresh-button":
            service.request_refresh()
        result, manifest, status, quotes, error, busy = service.snapshot()
        quote_children = [
            html.Strong("BLOOMBERG PREVIEW"),
            html.Span(error or "Latest available quotes · separate from daily index"),
        ]
        if quotes:
            for q in quotes["quotes"]:
                quote_children.append(
                    html.Span(
                        [
                            html.B(q["security"] + " "),
                            f"{q['value']:,.2f}",
                            html.Small(
                                f"Vendor date/time: {q['quote_date']} {q['quote_time']}"
                            ),
                        ],
                        className="quote-item",
                    )
                )
            quote_children.append(
                html.Small(
                    "Retrieved: "
                    + quotes["fetched_at"]
                    + (" · cached after connection failure" if error else "")
                )
            )
        if result is None:
            return (
                html.Div(
                    [
                        html.H2("Waiting for source history"),
                        html.P(
                            "Run python start.py --update --refresh on the signed-in Bloomberg workstation, then refresh this page."
                        ),
                        html.Code(status),
                    ],
                    className="empty-state",
                ),
                status,
                quote_children,
                {"display": "none"},
                busy,
            )
        now = pd.Timestamp.now(tz="America/Toronto").date()
        age = (now - result.history.index[-1].date()).days
        banner = [
            html.Span("DAILY HISTORY", className="status-label"),
            html.Span(
                f"Through {manifest['last_date']} · "
                + ("STALE CACHE · " if age > 4 else "")
                + status
            ),
        ]
        if any(r["review"] for r in manifest["coverage"]):
            banner.append(
                html.Span(
                    "Research preview · source definitions under review",
                    className="review-note",
                )
            )
        content = {
            "overview": lambda: overview(result),
            "timeline": lambda: timeline(result, start, end),
            "data": lambda: coverage_view(result, manifest, selected_date),
            "methodology": lambda: methodology(service.config),
        }[view]()
        return (
            content,
            banner,
            quote_children,
            {"display": "flex" if view in ("timeline", "data") else "none"},
            busy,
        )

    @app.server.get("/download/<name>")
    def download(name):
        if name not in {
            "history.csv",
            "weights.csv",
            "coverage.csv",
            "signals.csv",
            "weight-changes.csv",
        }:
            abort(404)
        path = ROOT / "index-results" / name
        if not path.exists():
            abort(404)
        return send_file(path, as_attachment=True, download_name="canadian-fg-" + name)

    if start_worker:
        service.start()
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use cached sources without network requests",
    )
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()
    print(
        f"\nCanadian Fear & Greed Index\nOpen in your browser: http://127.0.0.1:{args.port}\nKeep this terminal open. Press Ctrl+C to stop.\n",
        flush=True,
    )
    create_app(offline=args.offline, start_worker=True).run(
        host="127.0.0.1", port=args.port, debug=False
    )
