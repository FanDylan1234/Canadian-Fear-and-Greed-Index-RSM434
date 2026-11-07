import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from test_index import fixture
from fgindex.data import load_config, read_inputs
from fgindex.pipeline import build
import start

class StartupAndDateTests(unittest.TestCase):
    def test_missing_optional_files_keep_dates_and_pipeline_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / 'raw'
            raw.mkdir()
            source = fixture()
            for name in source.columns:
                if name in ('canada_vixi_history', 'mx_equity_put_call', 'fred_vix'):
                    continue
                source[name].rename('value').to_csv(raw / (name + '.csv'), index_label='date')
            inputs, _ = read_inputs(raw, load_config())
            self.assertIsInstance(inputs.index, pd.DatetimeIndex)
            with patch('fgindex.data_checks.yesterday', return_value='2012-12-30'):
                result, _ = build(raw, Path(folder) / 'output')
            self.assertLessEqual(result.history.index.max(), pd.Timestamp('2012-12-30'))
            self.assertTrue((Path(folder) / 'output/history.csv').exists())

    def test_launcher_selects_task_and_forwards_options(self):
        for arguments, module, remaining in [
            (["--offline"], "app", ["--offline"]),
            (["--update", "--refresh"], "update_index", ["--refresh"]),
            (["--check-data"], "run_all_checks", []),
        ]:
            with self.subTest(arguments=arguments), patch(
                "sys.argv", ["start.py", *arguments]
            ), patch("start.run", return_value=0) as launch:
                self.assertEqual(start.main(), 0)
                launch.assert_called_once_with(module, remaining)

    def test_launcher_rejects_unsupported_existing_environment(self):
        with patch('pathlib.Path.exists', return_value=True), patch('start.supported', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'existing .venv'):
                start.prepare_environment()
