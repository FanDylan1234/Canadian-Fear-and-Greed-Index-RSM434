import tempfile
import unittest
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import pandas as pd
from test_index import fixture
from index_engine.loadpulleddata import load_config, read_inputs
from index_engine.pipeline import build
import runtostartindex as start

class StartupAndDateTests(unittest.TestCase):
    def test_checkout_initializes_and_reuses_its_own_cache(self):
        from index_engine.service import DashboardService
        with tempfile.TemporaryDirectory() as folder, patch('index_engine.service.ROOT', Path(folder)):
            cache = Path(folder) / 'data-access-results' / 'raw'
            service = DashboardService(offline=True)
            self.assertEqual(service.raw_dir, cache)
            saved = cache / 'saved.csv'
            saved.write_text('existing')
            DashboardService(offline=True)
            self.assertEqual(saved.read_text(), 'existing')

    def test_first_online_refresh_runs_even_immediately_after_machine_boot(self):
        from index_engine.service import DashboardService
        with tempfile.TemporaryDirectory() as folder:
            service = DashboardService(raw_dir=Path(folder) / 'raw')
            with patch('index_engine.service.time.monotonic', return_value=1), patch(
                'index_engine.liverefresh.refresh_daily', return_value={'errors': [], 'status': 'Updated'}
            ) as refresh, patch('index_engine.liverefresh.quote_snapshot'), patch.object(
                service.wake, 'wait', side_effect=lambda _: service.stop.set()
            ):
                service._run()
            refresh.assert_called_once_with(service.raw_dir)

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
            with patch('index_engine.data_checks.yesterday', return_value='2012-12-30'):
                result, manifest = build(raw, Path(folder) / 'output')
            self.assertLessEqual(result.history.index.max(), pd.Timestamp('2012-12-30'))
            self.assertTrue((Path(folder) / 'output/history.csv').exists())
            with ZipFile(Path(folder) / 'output/holdout-audit.zip') as archive:
                calibration = archive.read('calibration.json')
                self.assertEqual(hashlib.sha256(calibration).hexdigest(), manifest['holdout']['calibration_sha256'])
                self.assertEqual(json.loads(calibration)['models'], result.research.calibration['models'])
                exported = pd.read_csv(archive.open('observations.csv'))
                self.assertIn('index_sentiment', exported)
                self.assertNotIn('index_quintile', exported)

    def test_launcher_selects_task_and_forwards_options(self):
        for arguments, module, remaining in [
            (["--offline"], "dashdesign", ["--offline"]),
            (["--update", "--refresh"], "update_index", ["--refresh"]),
            (["--check-data"], "run_all_checks", []),
        ]:
            with self.subTest(arguments=arguments), patch(
                "sys.argv", ["runtostartindex.py", *arguments]
            ), patch("runtostartindex.run", return_value=0) as launch:
                self.assertEqual(start.main(), 0)
                launch.assert_called_once_with(module, remaining)

    def test_launcher_rejects_unsupported_existing_environment(self):
        with patch('pathlib.Path.exists', return_value=True), patch('runtostartindex.supported', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'existing .venv'):
                start.prepare_environment()
