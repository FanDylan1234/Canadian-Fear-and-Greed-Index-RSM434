"""One command: refresh sources, construct index, save diagnostics and chart."""

import argparse
from pathlib import Path
from index_engine.data import ROOT, load_config
from index_engine.pipeline import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Pull Bloomberg and public histories first",
    )
    parser.add_argument(
        "--raw-dir", type=Path, default=ROOT / "data-access-results/raw"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "index-results")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    status = None
    if args.refresh:
        from index_engine.live import refresh_daily

        status = refresh_daily(args.raw_dir)
        print(status["status"])
        for error in status["errors"]:
            print("  " + error)
    result, manifest = build(args.raw_dir, args.output, load_config(args.config))
    from index_engine.charts import history_chart

    history_chart(result.history).write_html(
        args.output / "index-chart.html", include_plotlyjs=True
    )
    print(f"Saved {len(result.history):,} sessions to {args.output}")
    print(f"Coverage: {manifest['first_score']} to {manifest['last_date']}")
    print(result.history.tail(1).to_string())
    return 1 if status and status["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
