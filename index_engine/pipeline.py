"""Build the daily index and save CSV outputs and source records."""

import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import os
import pandas as pd
from .loadpulleddata import ROOT, load_config, read_inputs
from .buildindicatorsfromdata import build_index
from .holdout import evaluate, training_fingerprint, CALIBRATION_FILE, SWITCH_COST
from .research_export import audit_bundle


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {"mode": "wb"} if isinstance(data, bytes) else {"mode": "w", "encoding": "utf-8"}
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp", **options) as handle:
        handle.write(data)
        temp = handle.name
    os.replace(temp, path)


atomic_text = atomic_write  # Used by the source refreshers for text files.


def clean_json(value):
    # pandas handles numpy scalars, NaN and dates consistently for browser JSON.
    return json.loads(pd.Series([value]).to_json(orient="values", date_format="iso"))[0]


def build(raw_dir=None, output=None, config=None):
    raw_dir, output = Path(raw_dir or ROOT / "data-access-results/raw"), Path(
        output or ROOT / "index-results"
    )
    config = config or load_config()
    inputs, coverage = read_inputs(raw_dir, config)
    # Today's unfinished daily observations are never admitted to the research history.
    from index_engine.data_checks import yesterday

    inputs = inputs.loc[inputs.index <= pd.Timestamp(yesterday())]
    result = build_index(inputs, config)
    if not result.history["index"].notna().any():
        raise ValueError(
            "Insufficient history for five warmed-up components; index not published."
        )
    combined = result.history.join(result.scores.add_prefix("score_")).join(
        result.weights.add_prefix("weight_")
    )
    artifacts = {
        "history.csv": combined,
        "signals.csv": result.signals,
        "weights.csv": result.weights,
        "coverage.csv": pd.DataFrame(coverage),
    }
    for name, frame in artifacts.items():
        atomic_text(
            output / name,
            frame.to_csv(index=name != "coverage.csv", index_label="date"),
        )
    changes = result.weights.ne(result.weights.shift()).any(axis=1)
    weight_periods = result.weights.loc[changes].copy()
    atomic_text(
        output / "weight-changes.csv", weight_periods.to_csv(index_label="date")
    )
    manifest = dict(
        built_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        config=config,
        config_sha256=hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest(),
        raw_sha256={row["dataset"] + ".csv": row["sha256"] for row in coverage if row["sha256"]},
        first_date=str(result.history.index[0].date()),
        last_date=str(result.history.index[-1].date()),
        first_score=str(result.history["index"].first_valid_index().date()),
        coverage=coverage,
    )
    research = evaluate(result, inputs, config)
    current_training_hash = training_fingerprint(research.audit)
    manifest["holdout"] = {
        "calibration_sha256": hashlib.sha256(CALIBRATION_FILE.read_bytes()).hexdigest(),
        "frozen_training_sha256": research.calibration["train_sha256"],
        "current_training_sha256": current_training_hash,
        "training_matches_freeze": current_training_hash == research.calibration["train_sha256"],
        "switch_cost_fraction": SWITCH_COST,
        "source_files": {name: hashlib.sha256((ROOT / "index_engine" / name).read_bytes()).hexdigest()
                         for name in ("buildindicatorsfromdata.py", "holdout.py", "loadpulleddata.py")},
    }
    result.research = research
    atomic_write(output / "holdout-audit.zip", audit_bundle(research, manifest))
    atomic_text(output / "manifest.json", json.dumps(clean_json(manifest), indent=2))
    return result, manifest
