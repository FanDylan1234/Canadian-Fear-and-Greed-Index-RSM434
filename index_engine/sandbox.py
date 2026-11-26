"""Browser-local weight experiments; never modify the published index or research."""

import base64
import binascii
from io import StringIO

import numpy as np
import pandas as pd

from .buildindicatorsfromdata import COMPONENTS, past_percentile, regime

POLL_SOURCE = "https://nanos.co/dataportal/nanos-bloomberg-tracking-methodology/"
POLLS = {
    "confidence": ("Bloomberg Nanos confidence", "Overall Canadian consumer confidence."),
    "expectations": ("Bloomberg Nanos expectations", "Outlook for the economy and local property values."),
    "pocketbook": ("Bloomberg Nanos pocketbook", "Personal finances and job security."),
}
INDICATORS = {**{k: (v[0], v[1]) for k, v in COMPONENTS.items()}, **POLLS}
POLL_WINDOW, POLL_MINIMUM, POLL_MAX_AGE = 52, 26, 14
MAX_UPLOAD = 1_000_000


def parse_polls(contents):
    """Validate published weekly values, not observation-week dates or made-up scores."""
    try:
        if not isinstance(contents, str) or len(contents) > MAX_UPLOAD * 1.4:
            raise ValueError("Choose a CSV smaller than 1 MB.")
        payload = base64.b64decode(contents.split(",", 1)[1], validate=True)
        if len(payload) > MAX_UPLOAD:
            raise ValueError("Choose a CSV smaller than 1 MB.")
        frame = pd.read_csv(StringIO(payload.decode("utf-8-sig")), dtype=str)
    except (IndexError, UnicodeError, binascii.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError("Upload a UTF-8 CSV with release_date and poll columns.") from exc
    keys = [key for key in POLLS if key in frame]
    if "release_date" not in frame or not keys or set(frame) - {"release_date", *POLLS}:
        raise ValueError("Use release_date and one or more of confidence, expectations, pocketbook.")
    if frame.empty or len(frame) > 5000:
        raise ValueError("Include between 1 and 5,000 dated releases.")
    if not frame.release_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False).all():
        raise ValueError("Release dates must use YYYY-MM-DD.")
    dates = pd.to_datetime(frame.release_date, format="%Y-%m-%d", errors="coerce")
    today = pd.Timestamp.now(tz="America/Toronto").tz_localize(None).normalize()
    if dates.isna().any() or dates.duplicated().any() or (dates > today).any():
        raise ValueError("Release dates must be valid, unique and no later than today.")
    for key in keys:
        values = pd.to_numeric(frame[key], errors="coerce")
        if (frame[key].notna() & values.isna()).any() or not values.dropna().between(0, 100).all():
            raise ValueError(f"{key}: use published values from 0 to 100, or leave a cell blank.")
        frame[key] = values
        released = dates[values.notna()].sort_values()
        if released.diff().dropna().dt.days.lt(4).any():
            raise ValueError(f"{key}: include weekly releases, not repeated daily values.")
    if frame[keys].notna().sum().sum() == 0:
        raise ValueError("Include at least one published poll value.")
    frame["release_date"] = dates.dt.strftime("%Y-%m-%d")
    frame = frame.sort_values("release_date")
    # Plain JSON scalars only; missing values become null for the browser store.
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def poll_scores(records, calendar):
    scores = pd.DataFrame(np.nan, index=calendar, columns=list(POLLS))
    releases = pd.DataFrame(pd.NaT, index=calendar, columns=list(POLLS))
    if not records:
        return scores, releases
    frame = pd.DataFrame(records).set_index("release_date")
    frame.index = pd.to_datetime(frame.index)
    for key in POLLS:
        if key not in frame:
            continue
        weekly = frame[key].dropna().astype(float).sort_index()
        if weekly.empty:
            continue
        ranked = past_percentile(weekly, POLL_WINDOW, POLL_MINIMUM)
        # Release times are unknown. Admit a release only on a later TSX session.
        matched = pd.merge_asof(pd.DataFrame({"session": calendar}),
                                pd.DataFrame({"release": weekly.index, "score": ranked.to_numpy()}),
                                left_on="session", right_on="release", direction="backward",
                                allow_exact_matches=False, tolerance=pd.Timedelta(days=POLL_MAX_AGE))
        scores[key] = matched.score.to_numpy()
        releases[key] = matched.release.to_numpy()
    return scores, releases


def custom_index(result, selected, relative_weights, records=None):
    """Normalize positive weights among available selected scores on each date.

    Experiments need one available score. The official index retains its five-score rule.
    Returns new objects; no shared IndexResult state is changed.
    """
    extra, releases = poll_scores(records, result.scores.index)
    scores = result.scores.join(extra)
    requested = pd.Series({key: relative_weights.get(key, 0) if key in selected else 0
                          for key in INDICATORS}, dtype=float).fillna(0)
    if not np.isfinite(requested).all() or not requested.between(0, 100).all():
        raise ValueError("Relative weights must be numbers from 0 to 100.")
    available = scores.notna().mul(requested, axis=1)
    totals = available.sum(axis=1)
    weights = available.div(totals.replace(0, np.nan), axis=0).fillna(0)
    values = scores.mul(weights).sum(axis=1).where(totals > 0)
    history = pd.DataFrame({"index": values, "regime": values.map(regime),
                            "active_components": weights.gt(0).sum(axis=1)}, index=scores.index)
    return history, scores, weights, releases
