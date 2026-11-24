"""Desktop Bloomberg adapter. Quotes are never inserted into daily research data."""

import datetime as dt
import json
import math
from pathlib import Path
from .loadpulleddata import ROOT, first_tsx_basis_break, load_config
from .pipeline import atomic_text
from index_engine.pull_bloomberg import BloombergClient
from index_engine.pull_data import parse, SOURCES
import urllib.request


def refresh_daily(raw_dir=None, client_factory=BloombergClient):
    from index_engine.data_checks import yesterday

    raw_dir = Path(raw_dir or ROOT / "data-access-results/raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_path = raw_dir.parent / "bloomberg-report.json"
    old = (
        json.loads(report_path.read_text(encoding="utf-8-sig"))
        if report_path.exists()
        else {"results": []}
    )
    previous = {r["id"]: r for r in old.get("results", [])}
    specs = json.loads((ROOT / "support" / "config" / "bloomberg-series.json").read_text(encoding="utf-8-sig"))
    results, errors = [], []
    review_required = False
    client = None
    try:
        try:
            client = client_factory()
        except Exception as exc:
            errors.append("Bloomberg connection: " + str(exc))
        for spec in specs:
            name = spec["id"]
            prior = previous.get(name, {})
            if review_required:
                results.append(dict(prior, id=name, refresh_status="Skipped: Bloomberg workflow review"))
                continue
            # Never rerun candidate discovery silently during normal refresh.
            explicit = spec.get("verified") and spec.get("field")
            security = (
                spec.get("security")
                if explicit
                else prior.get("security") or spec.get("security")
            )
            field = (
                spec.get("field")
                if explicit
                else prior.get("field")
                or spec.get("field")
                or next(iter(spec.get("fields", [])), None)
            )
            row = dict(prior) if prior else dict(id=name)
            row.update(security=security, field=field)
            try:
                if client is None:
                    raise RuntimeError("Desktop API unavailable; retained cached data")
                if not security or not field:
                    raise RuntimeError(
                        "Mapping unresolved; run data discovery and review metadata"
                    )
                end = min(yesterday(), spec.get("expected_end", yesterday()))
                start = load_config()["history_start"]
                if name in ("canada_vixc_history", "canada_vixi_history"):
                    start = max(start, spec["expected_start"])
                import pandas as pd

                old_file = raw_dir / (name + ".csv")
                old_frame = None
                request_start = start
                same_mapping = prior.get("security") == security and prior.get("field") == field
                cached_start = prior.get("history_start") or prior.get("coverage", {}).get("expected_start")
                # RT116 is rebased to the first date of each Bloomberg historical request.
                # Replace it with one fixed-start path. A moving overlap can splice two bases.
                fixed_base = name == "tsx_total_return" and field == "TOT_RETURN_INDEX_GROSS_DVDS"
                if not fixed_base and same_mapping and cached_start == start and old_file.exists():
                    old_frame = pd.read_csv(old_file)
                    latest = dt.date.fromisoformat(old_frame.date.max())
                    request_start = max(start, (latest - dt.timedelta(days=7)).isoformat())
                if name == "tsx_price" and not old_file.exists():
                    probe_start = max(start, (dt.date.fromisoformat(end) - dt.timedelta(days=6)).isoformat())
                    print(f"[Data] Testing Bloomberg TSX history access: {probe_start} through {end}", flush=True)
                    try:
                        client.history(security, field, probe_start, end)
                    except RuntimeError as exc:
                        if "WORKFLOW_REVIEW_NEEDED" in str(exc):
                            raise RuntimeError(f"Recent TSX access check ({probe_start} to {end}): {exc}") from exc
                        # A holiday week can be empty even when the full history is available.
                        if "No numeric historical observations" not in str(exc):
                            raise
                    else:
                        print("[Data] Recent TSX history access confirmed.", flush=True)
                print(f"[Data] {name}: requesting {request_start} through {end}", flush=True)
                rows = client.history(security, field, request_start, end)

                frame = pd.DataFrame(rows)
                if frame.date.duplicated().any() or not frame.value.notna().any():
                    raise ValueError("Duplicate dates or empty history")
                if old_frame is not None:
                    if frame.date.max() < old_frame.date.max():
                        raise ValueError("Refresh shortened historical coverage; retained cache")
                    frame = frame.set_index("date").combine_first(old_frame.set_index("date")).sort_index().reset_index()
                    rows = frame.astype(object).where(frame.notna(), None).to_dict("records")
                from index_engine.data_checks import check_history

                quality = check_history(rows, spec, start, end)
                if "COUNTS_NOT_NONNEGATIVE_INTEGERS" in quality["issues"]:
                    raise ValueError("Invalid count values; retained cache")
                numeric = pd.to_numeric(frame.value, errors="raise").dropna()
                if not numeric.map(math.isfinite).all() or (numeric < 0).any():
                    raise ValueError("Invalid numeric values; retained cache")
                if spec.get("kind") in ("level", "volatility") and (numeric <= 0).any():
                    raise ValueError("Nonpositive level; retained cache")
                if old_frame is None and old_file.exists():
                    old_frame = pd.read_csv(old_file)
                if old_frame is not None:
                    if (
                        frame.date.min() > old_frame.date.min()
                        or frame.date.max() < old_frame.date.max()
                    ):
                        raise ValueError(
                            "Refresh shortened historical coverage; retained cache"
                        )
                if fixed_base:
                    if old_frame is not None:
                        existing_dates = old_frame.loc[old_frame.value.notna(), "date"]
                        if not existing_dates.isin(frame.loc[frame.value.notna(), "date"]).all():
                            raise ValueError("Fixed-start TSX return history lost cached observations")
                    price = pd.read_csv(raw_dir / "tsx_price.csv", parse_dates=["date"]).set_index("date").value
                    levels = frame.set_index(pd.to_datetime(frame.date)).value
                    broken = first_tsx_basis_break(levels, price)
                    if broken is not None:
                        raise ValueError(f"TSX return history changes scale on {broken:%Y-%m-%d}")
                metadata = prior.get("metadata") if same_mapping else None
                metadata = metadata or client.metadata(security, field)
                if name in ("tsx_advancing", "tsx_declining"):
                    names = [
                        d.get("fieldData", {}).get("NAME", "")
                        for msg in metadata.get("security_details", [])
                        for d in msg.get("securityData", [])
                    ]
                    if (
                        not names
                        or any("venture" in n.lower() for n in names)
                        or not any("composite" in n.lower() for n in names)
                    ):
                        raise ValueError(
                            "Breadth metadata does not confirm Composite; cache retained"
                        )
                atomic_text(old_file, frame.to_csv(index=False))
                row.update(
                    metadata=metadata,
                    coverage=quality,
                    refresh_status="Updated",
                    history_start=start,
                    refreshed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                )
                if fixed_base:
                    row["return_index_base_start"] = request_start
                row["definition_verified"] = bool(
                    spec.get("verified", False)
                    if explicit
                    else prior.get("definition_verified", False)
                )
            except Exception as exc:
                review_required = "WORKFLOW_REVIEW_NEEDED" in str(exc)
                row["refresh_status"] = ("Retained cache: " if (raw_dir / (name + ".csv")).exists() else "Download failed: ") + str(exc)
                errors.append(name + ": " + str(exc))
                print(f"[Data] {name} failed: {exc}", flush=True)
            results.append(row)
    finally:
        if client is not None:
            client.close()
    atomic_text(
        report_path, json.dumps(dict(old, results=results), indent=2, default=str)
    )
    vix_note = ""
    # US VIX can use the official Cboe distributor when FRED is unreachable.
    for source, url, _, _ in SOURCES:
        if source not in ("fred_vix", "mx_equity_put_call"):
            continue
        print(f"[Data] Refreshing {source}", flush=True)
        try:
            if source == "fred_vix":
                from .us_vix import refresh_vix
                provenance = refresh_vix(raw_dir, load_config()["history_start"], yesterday())
                vix_note = "US VIX: " + provenance["provider"] + " through " + provenance["last"]
                continue
            request = urllib.request.Request(
                url, headers={"User-Agent": "CanadianFG-research/1.0"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8-sig")
            rows = parse(source, text)
            if not any(value is not None for _, value in rows):
                raise ValueError("Empty numeric history")
            atomic_text(raw_dir / (source + ".csv"), text)
        except Exception as exc:
            errors.append(source + ": " + str(exc))
    status = dict(
        at=dt.datetime.now(dt.timezone.utc).isoformat(),
        errors=errors,
        status=("Updated" if not errors else "Partial refresh / cached inputs retained") + ("; " + vix_note if vix_note else ""),
    )
    atomic_text(raw_dir.parent / "refresh-status.json", json.dumps(status, indent=2))
    return status


def quote_snapshot(client_factory=BloombergClient):
    client = client_factory()
    try:
        messages = client.request(
            "//blp/refdata",
            "ReferenceDataRequest",
            {},
            {
                "securities": ["SPTSX Index", "VIXI Index"],
                "fields": ["PX_LAST", "LAST_UPDATE_DT", "LAST_UPDATE"],
            },
        )
        quotes = []
        for msg in messages:
            for row in msg.get("securityData", []):
                if row.get("securityError"):
                    raise RuntimeError(str(row["securityError"]))
                fields = row.get("fieldData", {})
                price = fields.get("PX_LAST")
                if (
                    price is None
                    or not math.isfinite(float(price))
                    or float(price) <= 0
                ):
                    continue
                quotes.append(
                    dict(
                        security=row["security"],
                        value=float(price),
                        quote_date=str(fields.get("LAST_UPDATE_DT", "Unavailable")),
                        quote_time=str(fields.get("LAST_UPDATE", "Unavailable")),
                        field_errors=row.get("fieldExceptions", []),
                    )
                )
        if not quotes:
            raise RuntimeError("No entitled Bloomberg quotes returned")
        return dict(
            fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            quotes=quotes,
            note="Polling snapshot, not a streaming subscription; vendor timestamp determines freshness.",
        )
    finally:
        client.close()
