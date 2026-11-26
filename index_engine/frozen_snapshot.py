"""Freeze cached calculations once, then load them without downloads or runtime writes."""

import argparse
from dataclasses import fields
from io import BytesIO, StringIO
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

from .buildindicatorsfromdata import IndexResult
from .holdout import Research
from .loadpulleddata import ROOT

SNAPSHOT = ROOT / 'demo' / 'snapshot.zip'
FORMAT = 1
INDEX_FRAMES = ('history', 'signals', 'scores', 'weights', 'inputs')
RESEARCH_FRAMES = tuple(f.name for f in fields(Research) if f.name != 'calibration')
DOWNLOADS = {'history.csv', 'weights.csv', 'coverage.csv', 'signals.csv', 'weight-changes.csv',
             'holdout-audit.zip', 'observations.csv', 'calibration.json', 'episodes.csv',
             'vix-comparison.csv', 'backtest-ledger.csv'}


def write_snapshot(result, manifest, output, destination=SNAPSHOT):
    if result.research is None or not result.history['index'].notna().any():
        raise ValueError('A calculated index and research results are required.')
    output, destination = Path(output), Path(destination)
    metadata = {'format': FORMAT, 'as_of': str(result.history.index[-1].date()),
                'manifest': manifest, 'calibration': result.research.calibration}
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('metadata.json', json.dumps(metadata, indent=2))
        for group, obj, names in [('index', result, INDEX_FRAMES),
                                   ('research', result.research, RESEARCH_FRAMES)]:
            for name in names:
                archive.writestr(f'{group}/{name}.json', getattr(obj, name).to_json(
                    orient='table', date_format='iso', double_precision=15))
        for name in DOWNLOADS:
            if (output / name).is_file():
                archive.write(output / name, 'downloads/' + name)
        with ZipFile(output / 'holdout-audit.zip') as audit:
            for name in DOWNLOADS - {'holdout-audit.zip'}:
                if name in audit.namelist():
                    archive.writestr('downloads/' + name, audit.read(name))
    # Validate the completed archive before replacing an earlier snapshot.
    FrozenService(payload=buffer.getvalue())
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_bytes(buffer.getvalue())
    temporary.replace(destination)
    return metadata['as_of']


class FrozenService:
    frozen = True

    def __init__(self, path=SNAPSHOT, *, payload=None):
        if payload is None:
            if not Path(path).is_file():
                raise RuntimeError('Missing demo/snapshot.zip. On the computer with cached market data, '
                                   'run python runtostartindex.py --freeze, then copy demo/snapshot.zip '
                                   'into this branch. No Bloomberg connection is needed for the export.')
            payload = Path(path).read_bytes()
        with ZipFile(BytesIO(payload)) as archive:
            metadata = json.loads(archive.read('metadata.json'))
            if metadata['format'] != FORMAT:
                raise ValueError('Unsupported frozen snapshot format')

            def frame(group, name):
                return pd.read_json(StringIO(archive.read(f'{group}/{name}.json').decode()), orient='table')

            research = Research(calibration=metadata['calibration'],
                                **{name: frame('research', name) for name in RESEARCH_FRAMES})
            self.result = IndexResult(**{name: frame('index', name) for name in INDEX_FRAMES}, research=research)
            if self.result.history.empty or not self.result.history['index'].notna().any():
                raise ValueError('Snapshot has no published readings')
            if metadata['as_of'] != str(self.result.history.index[-1].date()):
                raise ValueError('Snapshot date does not match its history')
            self.downloads = {name: archive.read('downloads/' + name) for name in DOWNLOADS}
        self.manifest = metadata['manifest']
        self.config = dict(self.manifest['config'], snapshot_date=metadata['as_of'])
        self.status = f"Frozen evaluation edition · Data through {metadata['as_of']} · No live updates"

    def snapshot(self):
        return self.result, self.manifest, self.status, None, 'Live quotes are disabled in this edition.', False

    def request_refresh(self):
        pass

    def start(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, default=ROOT / 'data-access-results' / 'raw')
    parser.add_argument('--output', type=Path, default=SNAPSHOT)
    parser.add_argument('--check', action='store_true', help='Validate the committed snapshot without updating it')
    args = parser.parse_args()
    if args.check:
        print(FrozenService(args.output).status)
        return
    if not (args.raw_dir / 'tsx_price.csv').is_file():
        parser.error('No cached TSX data here. Run this export on the computer with data-access-results/raw.')
    import tempfile
    from .pipeline import build
    # Never refresh sources. Build outputs in a temporary directory; retain the original cache.
    with tempfile.TemporaryDirectory() as output:
        result, manifest = build(args.raw_dir, output)
        date = write_snapshot(result, manifest, output, args.output)
    print(f'Frozen data through {date}: {args.output}\nCopy this file into demo/snapshot.zip on frozen-demo.')


if __name__ == '__main__':
    main()
