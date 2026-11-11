"""US VIX daily closes: FRED first, official Cboe CSV on failure."""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import urllib.request
from pathlib import Path

CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

def decode_history(text, provider, start, end):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    date_key, value_key = ("observation_date", "VIXCLS") if provider == "FRED" else ("DATE", "CLOSE")
    if not {date_key, value_key}.issubset(reader.fieldnames or []):
        raise ValueError("Unexpected VIX CSV schema")
    result = {}
    for row in reader:
        date = (dt.date.fromisoformat(row[date_key]) if provider == "FRED"
                else dt.datetime.strptime(row[date_key], "%m/%d/%Y").date()).isoformat()
        if not start <= date <= end:
            continue
        if date in result:
            raise ValueError("Duplicate VIX dates")
        value = row[value_key].strip()
        value = None if value in ("", ".") else float(value)
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError("Invalid VIX close")
        result[date] = value
    if not any(v is not None for v in result.values()):
        raise ValueError("Empty VIX history")
    return dict(sorted(result.items()))

def refresh_vix(raw_dir, start, end, opener=None):
    # Same economic series via a different distributor, not Canadian volatility.
    from .pipeline import atomic_text
    opener = opener or urllib.request.urlopen
    path = Path(raw_dir) / "fred_vix.csv"  # Keep existing cache/schema compatible.
    previous = decode_history(path.read_text(encoding="utf-8-sig"), "FRED", start, end) if path.exists() else {}
    failures = []
    urls = [("FRED", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&cosd="+start+"&coed="+end),
            ("Cboe", CBOE_URL)]
    for provider, url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "CanadianFG-research/1.0"})
            with opener(request, timeout=10 if provider == "FRED" else 20) as response:
                rows = decode_history(response.read().decode("utf-8-sig"), provider, start, end)
            old_dates = {d for d, v in previous.items() if v is not None}
            new_dates = {d for d, v in rows.items() if v is not None}
            if not old_dates.issubset(new_dates):
                raise ValueError("Download lost cached observations")
            if (dt.date.fromisoformat(end)-dt.date.fromisoformat(max(new_dates))).days > 7:
                raise ValueError("Downloaded VIX history is stale")
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(["observation_date", "VIXCLS"])
            writer.writerows((d, "." if v is None else v) for d,v in rows.items())
            text = buffer.getvalue()
            provenance = dict(provider=provider, url=url, field="VIXCLS" if provider=="FRED" else "CLOSE",
                              first=min(new_dates), last=max(new_dates), failures=failures,
                              fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                              sha256=hashlib.sha256(text.encode()).hexdigest())
            atomic_text(path, text)
            atomic_text(path.parent / "us-vix-source.json", json.dumps(provenance, indent=2))
            return provenance
        except Exception as exc:
            failures.append(provider + ": " + str(exc))
    latest = max((d for d,v in previous.items() if v is not None), default="none")
    raise RuntimeError("; ".join(failures) + "; retained US VIX cache through " + latest)
