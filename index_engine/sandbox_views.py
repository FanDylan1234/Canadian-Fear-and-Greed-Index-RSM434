"""Persistent controls and isolated callbacks for the custom index tab."""

import hashlib
import json

import pandas as pd
from dash import Input, Output, State, ctx, dcc, html, no_update

from .buildindicatorsfromdata import COMPONENTS
from .dashboard_components import table
from .sandbox import INDICATORS, POLLS, POLL_SOURCE, custom_index, parse_polls


def sandbox_layout():
    def controls(keys):
        return html.Div([
            html.Div([
                dcc.Checklist(id=f"custom-use-{key}",
                              options=[{"label": title, "value": key}],
                              value=[key] if key in COMPONENTS else [],
                              persistence=True, persistence_type="session"),
                html.Small(description),
                html.Label("Relative weight", htmlFor=f"custom-weight-{key}"),
                dcc.Input(id=f"custom-weight-{key}", type="number", min=0, max=100,
                          step=1, value=1, debounce=False, persistence=True,
                          persistence_type="session"),
            ], className="custom-control") for key in keys
            for title, description in [INDICATORS[key]]
        ], className="custom-controls")

    return html.Section([
        html.Div([
            html.Div([html.H2("Build your index"),
                      html.P("Your own mix of Canadian market sentiment.", className="muted")]),
            html.Button("Reset to equal weights", id="custom-reset", n_clicks=0,
                        className="refresh-button"),
        ], className="section-heading"),
        html.P("Check an indicator to include it; uncheck it to remove it. Relative weights set its "
               "influence: 2 gives twice the weight of 1. The available selections always total 100%. "
               "Your choices apply only here and stay in this browser session.", className="muted"),
        html.Div(id="custom-reading", **{"aria-live": "polite"}),
        html.H3("Choose your market indicators"),
        controls(COMPONENTS),
        html.Details([
            html.Summary("Add a Bloomberg / Nanos survey"),
            html.P("These weekly Canadian surveys offer a household perspective. Expectations "
                   "looks ahead; Pocketbook describes personal circumstances. Overall confidence "
                   "combines both, so adding all three overlaps their information."),
            html.P([html.A("Read the Nanos methodology", href=POLL_SOURCE, target="_blank",
                           rel="noopener noreferrer"),
                    ". These are experimental additions, not validated predictors of TSX returns."]),
            controls(POLLS),
            html.H3("Import published survey history"),
            html.P("Upload a CSV with release_date (YYYY-MM-DD) and one or more columns named "
                   "confidence, expectations, pocketbook. Use published index levels from 0–100, "
                   "one row per weekly release. Use the publication date, not the survey week-end date."),
            html.P("Each survey is ranked against its previous 52 weekly releases, with 26 prior "
                   "releases required (at least 27 values for a score). Higher confidence means a "
                   "higher score. A release enters on the next observed TSX session and expires "
                   "after 14 calendar days. This keeps weekly polls separate from daily market data."),
            html.Div([
                dcc.Upload(id="custom-upload", children=html.Button("Upload survey CSV",
                           className="refresh-button"), accept=".csv,text/csv", multiple=False,
                           max_size=1_000_000),
                html.Button("Clear survey data", id="custom-clear", n_clicks=0,
                            className="refresh-button"),
                html.A("CSV column template", href="/assets/survey-template.csv", download="survey-template.csv"),
            ], className="custom-upload-actions"),
            html.P("No survey history loaded. Market indicators work immediately.",
                   id="custom-upload-status", role="status"),
            html.P("Uploads are used in memory for this browser tab and are not saved to source "
                   "files. Reloading the browser clears the upload.", className="muted"),
        ], className="quote-details"),
        html.P("Previous readings use today's chosen mix at each past date, with only the data "
               "available then. Missing selected indicators are excluded and the others share "
               "their weight. This experiment can use just one indicator; the published index "
               "requires five. Timeline, Prediction, Episodes, US VIX comparison, Backtest and "
               "Data & weights always use the published baseline.", className="muted"),
        dcc.Store(id="custom-polls"),
        dcc.Store(id="custom-render-key"),
    ], id="sandbox-panel", style={"display": "none"})


def register_sandbox(app, service, reading_summary):
    app.clientside_callback(
        "function(view) { return {display: view === 'sandbox' ? 'block' : 'none'}; }",
        Output("sandbox-panel", "style"), Input("view", "value"),
    )
    selections = [Input(f"custom-use-{key}", "value") for key in INDICATORS]
    weights = [Input(f"custom-weight-{key}", "value") for key in INDICATORS]

    @app.callback(
        [Output(f"custom-use-{key}", "value") for key in INDICATORS] +
        [Output(f"custom-weight-{key}", "value") for key in INDICATORS],
        Input("custom-reset", "n_clicks"), prevent_initial_call=True,
    )
    def reset(_):
        return [[key] if key in COMPONENTS else [] for key in INDICATORS] + [1] * len(INDICATORS)

    @app.callback(
        Output("custom-polls", "data"), Output("custom-upload-status", "children"),
        Input("custom-upload", "contents"), Input("custom-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    def upload(contents, _):
        if ctx.triggered_id == "custom-clear":
            return None, "Survey history cleared."
        if not contents:
            return no_update, no_update
        try:
            records = parse_polls(contents)
        except ValueError as exc:
            return no_update, f"Could not load survey: {exc} Previous upload retained."
        return records, (f"Loaded {len(records):,} weekly release rows, "
                         f"{records[0]['release_date']} to {records[-1]['release_date']}. "
                         "Check a survey above to include it. At least 27 values are needed for a score.")

    @app.callback(
        Output("custom-reading", "children"), Output("custom-render-key", "data"),
        Input("view", "value"), Input("ui-tick", "n_intervals"),
        Input("custom-polls", "data"), *selections, *weights,
        State("custom-render-key", "data"),
    )
    def render(view, tick, records, *values):
        if view != "sandbox":
            return no_update, no_update
        result, _, status, _, _, _ = service.snapshot()
        if result is None:
            return html.P("Market history is not available yet. " + status), None
        count = len(INDICATORS)
        selected = [key for key, value in zip(INDICATORS, values[:count]) if value and key in value]
        relative = dict(zip(INDICATORS, values[count:2*count]))
        cache_key = hashlib.sha256(json.dumps([id(result), selected, relative, records],
                                              sort_keys=True).encode()).hexdigest()
        if values[-1] == cache_key:
            return no_update, no_update
        try:
            history, scores, actual_weights, releases = custom_index(result, selected, relative, records)
        except ValueError as exc:
            return html.P(str(exc), role="status"), cache_key
        current, official = history["index"].iloc[-1], result.history["index"].iloc[-1]
        effective = actual_weights.iloc[-1]
        rows = []
        for key, (label, _) in INDICATORS.items():
            score, weight = scores[key].iloc[-1], effective[key]
            note = "Included" if weight else "Not selected" if key not in selected else "Zero weight"
            if key in selected and pd.isna(score):
                note = "Unavailable — excluded"
            if key in POLLS and pd.notna(releases[key].iloc[-1]):
                note += f" · release {releases[key].iloc[-1]:%b %d, %Y}"
            if key == "options" and result.history.options_carried_forward.iloc[-1]:
                note += f" · source {result.history.options_score_date.iloc[-1]:%b %d, %Y}"
            rows.append([label, f"{score:.1f}" if pd.notna(score) else "—", f"{weight:.2%}",
                         f"{weight * score:.2f}" if weight else "0.00", note])
        notices = []
        if pd.isna(current):
            notices.append(html.P("Select at least one available indicator with a positive weight "
                                  "to calculate your index.", role="status", className="custom-notice"))
        elif pd.notna(official):
            notices.append(html.P(f"Published index: {official:.2f} · Your index: {current:.2f} · "
                                  f"Difference: {current - official:+.2f} points.", className="custom-notice"))
        unavailable = [INDICATORS[key][0] for key in selected
                       if pd.isna(scores[key].iloc[-1]) and (relative[key] or 0) > 0]
        if unavailable:
            notices.append(html.P("No current score for: " + ", ".join(unavailable) +
                                  ". These selections have no weight today.", role="status"))
        return [reading_summary(history, prefix="custom", title="Your current reading"), *notices,
                html.Details([html.Summary("See how your current score adds up"),
                              table(["Indicator", "Score / 100", "Effective weight", "Index points", "Status"],
                                    rows, numeric_columns=(1, 2, 3))], className="quote-details")], cache_key
