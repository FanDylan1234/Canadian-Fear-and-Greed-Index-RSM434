from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from index_engine.frozen_snapshot import FrozenService, write_snapshot
from index_engine.pipeline import build
from index_engine.dashdesign import create_app
from test_index import fixture


class FrozenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        raw = folder / 'raw'
        raw.mkdir()
        source = fixture()
        source.index = pd.bdate_range('2017-01-02', periods=len(source))
        for name in source:
            date_key, value_key, sep = ('observation_date', 'VIXCLS', ',') if name == 'fred_vix' else (
                ('Date', 'Ratio', ';') if name == 'mx_equity_put_call' else ('date', 'value', ','))
            source[name].rename(value_key).to_csv(raw / (name + '.csv'), index_label=date_key, sep=sep)
        cls.result, cls.manifest = build(raw, folder / 'outputs')
        cls.path = folder / 'snapshot.zip'
        write_snapshot(cls.result, cls.manifest, folder / 'outputs', cls.path)

    def test_exact_snapshot_round_trip_without_network_or_rebuild(self):
        with patch('socket.socket', side_effect=AssertionError('Network attempted')), patch(
                'index_engine.pipeline.build', side_effect=AssertionError('Rebuild attempted')):
            service = FrozenService(self.path)
            for name in ('history', 'signals', 'scores', 'weights', 'inputs'):
                pd.testing.assert_frame_equal(getattr(service.result, name), getattr(self.result, name),
                                              check_freq=False, check_exact=False, atol=1e-12, rtol=1e-12)
            for name in ('audit', 'prediction', 'comparison', 'episodes', 'ledger', 'performance', 'inputs'):
                pd.testing.assert_frame_equal(getattr(service.result.research, name),
                                              getattr(self.result.research, name), check_freq=False,
                                              check_exact=False, atol=1e-12, rtol=1e-12)
            service.start()
            service.request_refresh()
            app = create_app(service=service, start_worker=True)
            client = app.server.test_client()
            layout = client.get('/_dash-layout').json
            def find(node, key):
                if isinstance(node, dict):
                    if node.get('props', {}).get('id') == key:
                        return node['props']
                    for v in node.values():
                        found = find(v, key)
                        if found: return found
                elif isinstance(node, list):
                    for v in node:
                        found = find(v, key)
                        if found: return found
            self.assertTrue(find(layout, 'ui-tick')['disabled'])
            self.assertEqual(find(layout, 'refresh-button')['style'], {'display': 'none'})
            for name, data in service.downloads.items():
                response = client.get('/download/' + name)
                self.assertEqual(response.status_code, 200, name)
                self.assertEqual(response.data, data, name)
            self.assertEqual(client.get('/download/metadata.json').status_code, 404)
            key = next(iter(app.callback_map))
            cb = app.callback_map[key]
            for view in ('overview', 'timeline', 'prediction', 'episodes', 'vix', 'backtest', 'data', 'methodology', 'sandbox'):
                values = [view, 0, 1, '2017-01-01', '2021-12-31', '2021-12-31']
                response = client.post('/_dash-update-component', json={
                    'output': key,
                    'outputs': [{'id': o.component_id, 'property': o.component_property} for o in cb['output']],
                    'inputs': [dict(i, value=v) for i, v in zip(cb['inputs'], values)],
                    'state': [{'id': 'render-key', 'property': 'data', 'value': None}],
                    'changedPropIds': ['refresh-button.n_clicks']})
                self.assertEqual(response.status_code, 200, response.data[:200])
                banner = str(response.json['response']['status-banner'])
                self.assertIn('Frozen evaluation edition', banner)
                self.assertNotIn('Refresh data to check', banner)

    def test_missing_snapshot_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError, 'Missing demo/snapshot.zip'):
            FrozenService(Path(self.temp.name) / 'missing.zip')


if __name__ == '__main__':
    unittest.main()
