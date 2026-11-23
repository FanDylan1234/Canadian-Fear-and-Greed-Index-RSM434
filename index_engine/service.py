"""Single-process local worker. Browser callbacks never wait on Bloomberg."""

import threading
import time
from pathlib import Path
from .loadpulleddata import ROOT, load_config
from .pipeline import build


class DashboardService:
    def __init__(self, offline=False, raw_dir=None, output=None):
        self.config = load_config()
        self.offline, self.output = offline, output
        self.raw_dir = Path(raw_dir) if raw_dir is not None else ROOT / "data-access-results" / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.result, self.manifest = None, None
        self.status = (
            "Cached daily observations" if offline else "Connecting to Bloomberg."
        )
        self.quote = None
        self.quote_error = "Offline mode" if offline else "Awaiting first quote"
        self.refreshing = False
        self.refresh_error = None
        self.rebuild()

    def rebuild(self):
        try:
            result, manifest = build(self.raw_dir, self.output, self.config)
            with self.lock:
                self.result, self.manifest = result, manifest
        except Exception as exc:
            with self.lock:
                self.status = "Build unavailable: " + str(exc)
                if self.refresh_error:
                    self.status += " | Source errors: " + self.refresh_error

    def snapshot(self):
        with self.lock:
            return (
                self.result,
                self.manifest,
                self.status,
                self.quote,
                self.quote_error,
                self.refreshing,
            )

    def request_refresh(self):
        if self.offline:
            self.rebuild()
        else:
            self.wake.set()

    def start(self):
        if not self.offline:
            threading.Thread(
                target=self._run, daemon=True, name="bloomberg-worker"
            ).start()

    def _run(self):
        from .liverefresh import quote_snapshot, refresh_daily

        last_daily = None
        while not self.stop.is_set():
            requested = self.wake.is_set()
            self.wake.clear()
            if (
                last_daily is None
                or requested
                or time.monotonic() - last_daily
                >= self.config["daily_refresh_minutes"] * 60
            ):
                with self.lock:
                    self.refreshing = True
                    self.status = (
                        "Refreshing daily sources; cached readings remain visible."
                    )
                try:
                    report = refresh_daily(self.raw_dir)
                    with self.lock:
                        self.refresh_error = " | ".join(report["errors"]) or None
                        self.status = report["status"] + (
                            " \u00b7 " + " | ".join(report["errors"][:3])
                            if report["errors"]
                            else ""
                        )
                    self.rebuild()
                except Exception as exc:
                    with self.lock:
                        self.status = "Refresh failed; retained cache: " + str(exc)
                finally:
                    with self.lock:
                        self.refreshing = False
                    last_daily = time.monotonic()
            try:
                quote = quote_snapshot()
                with self.lock:
                    self.quote, self.quote_error = quote, ""
            except Exception as exc:
                with self.lock:
                    self.quote_error = "Bloomberg unavailable: " + str(exc)
            self.wake.wait(self.config["refresh_seconds"])
