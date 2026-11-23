import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from index_engine.liverefresh import refresh_daily


class HistoryRefreshTests(unittest.TestCase):
    def test_local_history_is_seeded_then_extended_and_survives_refusal(self):
        client = Mock()
        client.metadata.return_value = {"name": "TSX"}
        client.history.side_effect = [
            [{"date": "2020-01-02", "value": 100}, {"date": "2020-01-17", "value": 105}],
            [{"date": "2020-01-17", "value": 106}, {"date": "2020-01-20", "value": 107}],
            RuntimeError("-4002 WORKFLOW_REVIEW_NEEDED"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "support/config"
            config.mkdir(parents=True)
            spec = dict(id="tsx_price", security="SPTSX Index", field="PX_LAST", verified=True, kind="level")
            (config / "bloomberg-series.json").write_text(json.dumps([spec]))
            raw = root / "data-access-results/raw"
            with patch("index_engine.liverefresh.ROOT", root), patch("index_engine.liverefresh.SOURCES", []), patch(
                "index_engine.liverefresh.load_config", return_value={"history_start": "2020-01-01"}
            ), patch("index_engine.data_checks.yesterday", return_value="2020-01-20"):
                self.assertFalse(refresh_daily(raw, lambda: client)["errors"])
                self.assertFalse(refresh_daily(raw, lambda: client)["errors"])
                self.assertEqual([call.args[2] for call in client.history.call_args_list],
                                 ["2020-01-01", "2020-01-10"])
                file = raw / "tsx_price.csv"
                self.assertEqual(pd.read_csv(file).value.tolist(), [100, 106, 107])
                saved = file.read_bytes()
                self.assertIn("WORKFLOW_REVIEW_NEEDED", refresh_daily(raw, lambda: client)["errors"][0])
                self.assertEqual(file.read_bytes(), saved)
