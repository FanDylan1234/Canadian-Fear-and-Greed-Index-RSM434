"""Read existing project exports, preserve provenance, and screen input validity."""
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pull_data import parse

ROOT = Path(__file__).resolve().parents[1]


def load_config(path=None):
    config = json.loads(Path(path or ROOT / "index-config.json").read_text(encoding="utf-8-sig"))
    if not 1 <= config["rank_min_history"] <= config["rank_window"]:
        raise ValueError("Invalid scoring window")
    if not 1 <= config["minimum_components"] <= 7:
        raise ValueError("Invalid minimum component count")
    return config


def read_inputs(raw_dir, config):
    raw_dir = Path(raw_dir)
    specs = json.loads((ROOT / "bloomberg-series.json").read_text(encoding="utf-8-sig"))
    report_path = raw_dir.parent / "bloomberg-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig")) if report_path.exists() else {}
    metadata = {r["id"]: r for r in report.get("results", [])}
    series, coverage = {}, []
    for name in [s["id"] for s in specs] + ["fred_vix", "mx_equity_put_call"]:
        path = raw_dir / (name + ".csv")
        meta = metadata.get(name, {})
        status = "Available"
        if not path.exists():
            s = pd.Series(dtype=float)
            status = "Missing file"
        else:
            text = path.read_text(encoding="utf-8-sig").rstrip("\x00 \t\r\n")
            if name in ("fred_vix", "mx_equity_put_call"):
                frame = pd.DataFrame(parse(name, text), columns=["date", "value"])
            else:
                frame = pd.read_csv(io.StringIO(text))
            if not {"date", "value"}.issubset(frame.columns):
                raise ValueError(f"Invalid schema: {name}")
            dates = pd.to_datetime(frame.date, errors="raise")
            if dates.duplicated().any():
                raise ValueError(f"Duplicate dates: {name}")
            s = pd.Series(pd.to_numeric(frame.value, errors="raise").to_numpy(), index=dates, dtype=float).sort_index()
            s = s.replace([np.inf, -np.inf], np.nan)
            count = name in ("tsx_advancing", "tsx_declining", "tsx_52week_highs", "tsx_52week_lows")
            invalid = ((s < 0) | ((s % 1) != 0)) & s.notna() if count else (s <= 0 if name != "canada_ig_credit_spread" else s < 0)
            if invalid.any():
                raise ValueError(f"Invalid values in {name}: {int(invalid.sum())}")
        valid = s.dropna()
        names = [d.get("fieldData", {}).get("NAME", "") for msg in meta.get("metadata", {}).get("security_details", []) for d in msg.get("securityData", [])]
        if name in ("tsx_advancing", "tsx_declining"):
            if any("venture" in n.lower() for n in names):
                status = "Excluded: TSX Venture universe"
                s = s * np.nan
            if not meta.get("definition_verified", False) or not any("composite" in n.lower() and "venture" not in n.lower() for n in names):
                s = s * np.nan
                if not status.startswith("Excluded"):
                    status = "Excluded: Composite definition not verified"
        coverage.append(dict(dataset=name, first=str(valid.index.min().date()) if len(valid) else None,
                             last=str(valid.index.max().date()) if len(valid) else None, observations=len(valid),
                             status=status, security=meta.get("security", "Public source" if name in ("fred_vix", "mx_equity_put_call") else "Unrecorded"),
                             field=meta.get("field", ""), name=" / ".join(names),
                             review=not meta.get("definition_verified", False) if name in metadata else name not in ("fred_vix", "mx_equity_put_call")))
        series[name] = s
    frame = pd.DataFrame(series).sort_index()
    if frame.tsx_price.notna().sum() == 0:
        raise ValueError("No TSX price history. Run python update_index.py --refresh on the Bloomberg workstation.")
    return frame, coverage
