"""Dashboard pages, user controls, and downloadable reports."""

import argparse
import datetime as dt
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import pandas as pd
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from flask import abort, send_file
from index_engine.loadpulleddata import ROOT
from index_engine.buildindicatorsfromdata import COMPONENTS, regime
from index_engine.chartsdesign import gauge, history_chart, recent_trend, signal_chart, weights_chart, color
from index_engine.service import DashboardService
from index_engine.dashboard_components import table
from index_engine.research_views import TABS as RESEARCH_TABS, research_page

GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}


def score_badge(value):
    return html.Span(
        regime(value), className="badge", style={"--tone": color(value)}
    )


def comparison(history):
    date = history.index[-1]
    rows = []
    for label, target in [
        ("Previous close", date - pd.DateOffset(days=1)),
        ("1 week ago", date - pd.DateOffset(days=7)),
        ("1 month ago", date - pd.DateOffset(months=1)),
        ("1 year ago", date - pd.DateOffset(years=1)),
    ]:
        past = history.loc[:target]
        if len(past) and (target - past.index[-1]).days <= 7:
            value = past["index"].iloc[-1]
            dated = f"{past.index[-1]:%b %d, %Y}"
        else:
            value, dated = float("nan"), "No observation"
        rows.append(
            html.Div(
                [
                    html.Div([html.Strong(label), html.Small(dated)]),
                    score_badge(value),
                    html.Span(
                        f"{value:.0f}" if pd.notna(value) else "\u2014",
                        className="round-score",
                    ),
                ],
                className="comparison-row",
            )
        )
    return html.Section([html.H2("Previous readings"), *rows], className="comparisons")


def overview(result):
    history = result.history
    latest = history.iloc[-1]
    cards = []
    for key, (title, subtitle, rationale) in COMPONENTS.items():
        value = result.scores[key].iloc[-1]
        weight = result.weights[key].iloc[-1]
        score_date = result.history.index[-1]
        note = ""
        if pd.isna(value):
            note = "Waiting for enough source history."
        if key == "options" and pd.notna(latest.get("options_score_date")):
            score_date = pd.Timestamp(latest["options_score_date"])
            if latest.get("options_carried_forward", False):
                note = f"Publication delayed: using {score_date:%B %d, %Y} data in the index at {weight:.2%} weight."

        cards.append(
            html.Article(
                [
                    html.Div(
                        [
                            html.Div([html.H3(title), html.P(subtitle)]),
                            score_badge(value),
                        ],
                        className="indicator-heading",
                    ),
                    html.Div([
                        html.Div([html.Strong(f"{value:.1f}" if pd.notna(value) else "—"),
                                  html.Span(" / 100")], className="component-score"),
                        html.Small(f"Weight {weight:.2%}"),
                    ], className="indicator-reading"),
                    dcc.Graph(id=f"indicator-{key}", figure=signal_chart(result, key),
                              config=GRAPH_CONFIG, style={"height": "188px"}, responsive=True),
                    html.P(note, className="indicator-note", role="status") if note else None,
                    html.Details([
                        html.Summary(["How it works", html.Small(f"As of {score_date:%b %d, %Y}")]),
                        *[html.P(paragraph) for paragraph in rationale.split("\n\n")],
                    ], className="indicator-detail"),
                ],
                className="indicator",
            )
        )
    return [
        html.Div(
            [
                html.Section([
                    html.Div([html.H2("Current reading"),
                              html.Time(f"{history.index[-1]:%b %d, %Y}",
                                        dateTime=history.index[-1].date().isoformat())],
                             className="reading-heading"),
                    html.Div([
                        html.Div([html.Div([html.Strong(f"{latest['index']:.0f}" if pd.notna(latest["index"]) else "—"),
                                           html.Span(" / 100")], className="index-score"),
                                  score_badge(latest["index"])], className="reading-value"),
                        dcc.Graph(id="overview-gauge", figure=gauge(latest["index"]), config=GRAPH_CONFIG,
                                  responsive=True, style={"height": "168px"}),
                    ], className="reading-body"),
                    html.Div([html.Span("Past 3 months"),
                              dcc.Graph(id="overview-trend", figure=recent_trend(history),
                                        config=GRAPH_CONFIG, responsive=True, style={"height": "46px"})],
                             className="reading-trend"),
                ], className="reading-panel"),
                comparison(history),
            ],
            className="overview-grid",
        ),
        html.Div(
            [
                html.Div([html.H2("Market indicators"),
                          html.P("Available indicators are equally weighted.", className="muted")]),
                html.Span(
                    f"{int(latest.active_components)} of 7 available", className="pill"
                ),
            ],
            className="section-heading",
        ),
        html.Div(cards, className="indicator-grid"),
    ]


def timeline(result, start, end):
    frame = result.history.loc[start:end]
    valid = frame["index"].dropna()
    stats = [
        ("Lowest reading", f"{valid.min():.1f}" if len(valid) else "\u2014"),
        ("Highest reading", f"{valid.max():.1f}" if len(valid) else "\u2014"),
        ("Average reading", f"{valid.mean():.1f}" if len(valid) else "\u2014"),
        ("Sessions with a score", f"{len(valid):,}"),
    ]
    return [
        html.Div(
            [
                html.H2("Sentiment over time"),
                html.A(
                    "Download history \u2193",
                    href="/download/history.csv",
                    className="text-link",
                ),
            ],
            className="section-heading",
        ),
        html.P(
            "Daily readings since 2010.",
            className="muted",
        ),
        dcc.Graph(
            id="timeline-history", figure=history_chart(result.history, start, end),
            config={"displaylogo": False, "scrollZoom": False},
        ),
        html.Div(
            [
                html.Div([html.Small(label), html.Strong(value)])
                for label, value in stats
            ],
            className="stats-grid",
        ),
        html.H3("Indicator weights"),
        html.P(
            "Weights adjust when an indicator is missing. At least five indicators are required.",
            className="muted",
        ),
        dcc.Graph(
            id="timeline-weights", figure=weights_chart(result.weights.loc[start:end]), config=GRAPH_CONFIG
        ),
        html.P(
            "See Methodology for coverage gaps and source definitions.",
            className="muted",
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
                    (label + " (using " + pd.Timestamp(result.history.loc[selected, "options_score_date"]).strftime("%b %d, %Y") + " data)"
                     if key == "options" and result.history.loc[selected, "options_carried_forward"] else label),
                    f"{value:.2f}" if pd.notna(value) else "Unavailable",
                    f"{result.weights.loc[selected, key]:.2%}",
                ]
            )
    return [
        html.H2("Source coverage"),
        html.P(
            "Coverage shows the first and latest observations in each source file. Status identifies missing or excluded data.",
            className="muted",
        ),
        table(
            ["Dataset", "Bloomberg mapping", "First observation", "Latest", "Status"],
            [
                [
                    r["dataset"]
                    .replace("_", " ")
                    .replace("tsx", "TSX")
                    .replace("fred", "FRED")
                    .title(),
                    (r["security"] or "") + " / " + (r["field"] or ""),
                    r["first"] or "\u2014",
                    r["last"] or "\u2014",
                    r["status"],
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
                html.A("Download weights \u2193", href="/download/weights.csv"),
                html.A("Download coverage \u2193", href="/download/coverage.csv"),
            ],
            className="download-links",
        ),
    ]


def methodology(config):
    return [
        html.H2("How the index works"),
        html.H3("Seven indicators, one score"),
        html.P(
            f"Each indicator is ranked against the previous {config['rank_window']} TSX sessions, with at least {config['rank_min_history']} observations required. Higher scores indicate greater risk appetite. Put/call, volatility and credit scores are reversed so all seven measures use the same direction."
        ),
        table(
            ["Score", "Sentiment"],
            [
                ["0\u201324", "Extreme fear"],
                ["25\u201344", "Fear"],
                ["45\u201355", "Neutral"],
                ["Above 55\u201375", "Greed"],
                ["Above 75", "Extreme greed"],
            ],
        ),
        html.H3("Equal weights"),
        html.P(
            "The index averages the available scores. Each receives the same weight, and at least five are required. Missing data are excluded, except put/call: its latest available calculated score is carried forward and equally weighted until a new score is available. Its original date is displayed. No score is filled backward before options history or scoring warmup."
        ),
        html.H3("Sources and timing"),
        html.P(
            "Daily history ends at yesterday in Toronto. Bloomberg quotes appear under Data & weights. The put/call source can publish later than the other inputs."
        ),
        html.P(
            "Breadth and new highs and lows use TSX Composite members. Credit measures Canadian investment-grade corporate option-adjusted spreads. Safe-haven demand compares stock returns with the Canada Aggregate bond index, which includes government and corporate bonds."
        ),
        html.H3("Historical coverage"),
        html.P(
            "Options history begins in 2011. VIXC and VIXI are scored separately, with US VIX used during gaps or warmup periods. US VIX downloads try FRED first, then Cboe daily closes if FRED fails; Data & weights identifies the distributor. The selected volatility source is recorded in each exported row. Repeated volatility quotes are excluded from the tenth identical observation onward."
        ),
        html.P(
            "Historical data can be revised. The research tabs apply the baseline to a retrospective holdout beginning in 2020. The audit bundle identifies the input files used for each build."
        ),
    ]


def quote_details(quotes, error):
    rows = []
    for quote in (quotes or {}).get("quotes", []):
        date = str(quote["quote_date"])
        time = str(quote["quote_time"])
        timestamp = date if time == date or time == "Unavailable" else f"{date} {time}"
        rows.append([quote["security"], f"{quote['value']:,.2f}", timestamp])
    return html.Details(
        [
            html.Summary("Bloomberg quotes"),
            html.P(error, className="muted") if error else None,
            (
                table(["Security", "Latest quote", "Source timestamp"], rows)
                if rows
                else html.P("Quotes are not available.")
            ),
            html.P(
                "Quotes are shown separately from the daily index.", className="muted"
            ),
        ],
        className="quote-details",
    )


def create_app(offline=False, start_worker=False, service=None):
    service = service or DashboardService(offline=offline)
    app = Dash(
        __name__,
        assets_folder=str(ROOT / "support" / "assets"),
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
                                html.Img(
                                    src="/assets/maple-leaf.svg",
                                    className="brand-mark",
                                    alt="",
                                ),
                                html.Strong("Canadian Market Sentiment"),
                            ],
                            href="/",
                            className="brand",
                        ),
                        html.Button([html.Span("↻", **{"aria-hidden": "true"}), "Refresh data"],
                                    id="refresh-button", n_clicks=0, className="refresh-button"),
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
                                    html.H1(["Fear ", html.Em("&"), " Greed Index"]),
                                    html.P(
                                        "A daily, 0–100 measure of sentiment in Canadian equity markets.", className="lead"
                                    ),
                                ]
                            ),
                        ],
                        className="hero-heading",
                    ),
                    html.Div(id="status-banner", role="status"),
                    html.Nav(dcc.RadioItems(
                        id="view",
                        value="overview",
                        className="tabs", labelClassName="tab", labelStyle={"display": "flex"},
                        options=[
                            {"label": label, "value": value}
                            for label, value in [
                                ("Overview", "overview"),
                                ("Timeline", "timeline"),
                                *[(label, value) for value, label in RESEARCH_TABS.items()],
                                ("Data & weights", "data"),
                                ("Methodology", "methodology"),
                            ]
                        ],
                    ), **{"aria-label": "Dashboard views"}),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Date range"),
                                    dcc.DatePickerRange(
                                        id="date-range",
                                        start_date="2010-01-01",
                                        end_date=latest,
                                        display_format="MMM D, YYYY",
                                        min_date_allowed="2010-01-01",
                                        number_of_months_shown=1,
                                    ),
                                ],
                                className="timeline-controls",
                            ),
                            html.Div(
                                [
                                    html.Label("Weights as of"),
                                    dcc.DatePickerSingle(
                                        id="weight-date",
                                        date=latest,
                                        display_format="MMM D, YYYY",
                                        min_date_allowed="2010-01-01",
                                    ),
                                ],
                                className="weight-controls",
                            ),
                        ],
                        id="date-controls",
                        className="date-controls",
                    ),
                    html.Div(id="page-content", className="overview"),
                    html.Div(id="quote-strip"),
                    html.Footer(
                        [
                            html.Strong("Canadian Fear & Greed Index"),
                            html.Span("Bloomberg \xb7 Montr\xe9al Exchange \xb7 FRED"),
                        ]
                    ),
                ],
                className="container",
            ),
            dcc.Store(id="render-key"),
            dcc.Interval(id="ui-tick", interval=5000, n_intervals=0),
        ]
    )

    @app.callback(
        Output("page-content", "children"),
        Output("status-banner", "children"),
        Output("quote-strip", "children"),
        Output("date-controls", "style"),
        Output("refresh-button", "disabled"),
        Output("render-key", "data"),
        Input("view", "value"),
        Input("ui-tick", "n_intervals"),
        Input("refresh-button", "n_clicks"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("weight-date", "date"),
        State("render-key", "data"),
    )
    def render(view, tick, clicks, start, end, selected_date, previous_key):
        if ctx.triggered_id == "refresh-button":
            service.request_refresh()
        result, manifest, status, quotes, error, busy = service.snapshot()
        controls = {
            "display": "flex" if view in ("timeline", "data") else "none",
            "--timeline-display": "flex" if view == "timeline" else "none",
            "--weights-display": "flex" if view == "data" else "none",
        }
        quote_content = quote_details(quotes, error) if view == "data" else []
        if result is None:
            return (
                html.Div(
                    [
                        html.H2(
                            "Loading market history"
                            if busy
                            else "Market history unavailable"
                        ),
                        html.P(
                            "The first download is running. This page updates automatically."
                            if busy
                            else "See the refresh result below and the [Data] messages in your terminal."
                        ),
                        html.P(status, className="muted"),
                    ],
                    className="empty-state",
                ),
                [],
                quote_content,
                controls,
                busy,
                None,
            )
        age = (
            pd.Timestamp.now(tz="America/Toronto").date()
            - result.history.index[-1].date()
        ).days
        banner = []
        if busy:
            banner = [html.Span("Updating data\u2026")]
        elif age > 4:
            banner = [
                html.Span(
                    f"History last updated {manifest['last_date']}. Refresh data to check for new readings."
                )
            ]
        elif any(
            word in status.lower()
            for word in ("failed", "unavailable", "partial", "error")
        ):
            banner = [html.Span(status)]
        if result.history.iloc[-1].get("options_carried_forward", False):
            used = pd.Timestamp(result.history.iloc[-1]["options_score_date"])
            banner.append(html.Span(f"Put/call: using {used:%B %d, %Y} data in the index (publication delayed)."))
        # Keep charts and calendar focus intact when the polling tick has no new data.
        render_key = json.dumps([id(result), view, start, end, selected_date,
            (quotes or {}).get("fetched_at") if view == "data" else None,
            error if view == "data" else None])
        content = no_update
        if render_key == previous_key:
            quote_content = no_update
        if render_key != previous_key:
            if view in RESEARCH_TABS:
                content = research_page(view, result.research, manifest)
            else:
                content = {
                    "overview": lambda: overview(result),
                    "timeline": lambda: timeline(result, start, end),
                    "data": lambda: coverage_view(result, manifest, selected_date),
                    "methodology": lambda: methodology(service.config),
                }[view]()
            content = html.Div(content, key=view, **{"data-view": view})
        return content, banner, (no_update if render_key == previous_key else quote_content), controls, busy, render_key

    # Hide the old tab immediately while its replacement is being calculated.
    # A keyed page remount also prevents Plotly state being reused across tabs.
    app.clientside_callback(
        "function(view) { return view; }",
        Output("page-content", "className"), Input("view", "value"),
    )

    @app.server.get("/download/<name>")
    def download(name):
        output = Path(getattr(service, "output", None) or ROOT / "index-results")
        if name in {"holdout-audit.zip", "observations.csv", "calibration.json",
                    "episodes.csv", "vix-comparison.csv", "backtest-ledger.csv"}:
            bundle = output / "holdout-audit.zip"
            if not bundle.is_file():
                abort(404)
            if name == "holdout-audit.zip":
                data = bundle.read_bytes()
            else:
                with ZipFile(bundle) as archive:
                    data = archive.read(name)
            return send_file(BytesIO(data), as_attachment=True, download_name=name)
        if name not in {
            "history.csv",
            "weights.csv",
            "coverage.csv",
            "signals.csv",
            "weight-changes.csv",
        }:
            abort(404)
        path = output / name
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
