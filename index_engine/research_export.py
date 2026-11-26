"""One atomic research download per build, with full-precision CSVs and provenance."""

import json
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from .loadpulleddata import ROOT


def audit_bundle(research, manifest):
    reports = {
        "observations.csv": research.audit,
        "source-levels.csv": research.inputs,
        "predictions.csv": research.prediction,
        "vix-comparison.csv": research.comparison,
        "episodes.csv": research.episodes,
        "backtest-ledger.csv": research.ledger,
        "backtest-performance.csv": research.performance,
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, frame in reports.items():
            dated = name in {"observations.csv", "source-levels.csv", "backtest-ledger.csv"}
            archive.writestr(name, frame.to_csv(index=dated, index_label="date", lineterminator="\n"))
        archive.writestr("calibration.json", json.dumps(research.calibration, indent=2))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.write(ROOT / "support" / "docs" / "holdout.md", "README.md")
    return buffer.getvalue()
