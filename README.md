# Canadian Fear & Greed Index — frozen evaluation edition

This branch, **frozen-demo**, preserves the dashboard from `main` and runs it from one saved data snapshot. All nine tabs remain available, including the isolated **Build your index** weight sandbox. There are no live market requests, Bloomberg SDK requirements, refresh workers, or automatic data updates. The banner shows the fixed observation date.

**Snapshot status:** `demo/snapshot.zip` must be exported from the computer holding the real cached data. No synthetic readings are bundled. Local startup and Vercel builds stop with an explanation if the snapshot is missing.

## One-time export on the computer with data

The existing `data-access-results/raw` folder stays in place when switching Git branches. No Bloomberg Terminal connection is needed for this export.

```powershell
git fetch origin
git switch frozen-demo
python runtostartindex.py --freeze
```

The command reads the cached files, calculates the index/research once, and creates **demo/snapshot.zip**. It does not refresh or overwrite the source data. If the cache is elsewhere:

```powershell
python runtostartindex.py --freeze --raw-dir "C:\path\to\data-access-results\raw"
```

Copy the ZIP to `demo/snapshot.zip` in this checkout, or commit it from that computer:

```powershell
git add demo/snapshot.zip
git commit -m "Add frozen market data for evaluation"
git push origin frozen-demo
```

That single file contains the dated readings, charts' inputs, component scores, research results, calibration, source coverage and downloadable reports. Visitors never need access to the original machine. The snapshot is deliberately tracked on this branch; refresh it only by explicitly exporting and committing a replacement.

## Run without Bloomberg

After the snapshot is present:

```powershell
python runtostartindex.py
```

Open http://127.0.0.1:8050. First-time setup installs ordinary Python packages; it does not install or call Bloomberg. Python 3.12 is recommended. The original live implementation remains in the repository; the launcher on this branch defaults to the frozen edition.

## Host on Vercel

1. Import this GitHub repository into Vercel and choose **frozen-demo** as the deployment branch. For a persistent production link, set the project's Production Branch to `frozen-demo`.
2. Use the repository root and Flask framework detection. `app.py` exports the Flask app, `requirements.txt` declares dependencies, and `.python-version` selects Python 3.12. Keep the build command from `vercel.json`.
3. Deploy after committing `demo/snapshot.zip`. No Bloomberg credentials or environment variables are required. The build validates the snapshot and refuses to deploy without it.
4. To let evaluators open the link without signing in, check the deployment's access/protection settings and test the production URL in a signed-out browser.

Vercel serves the Flask/Dash callbacks while every calculation uses the committed snapshot. The weight sandbox remains interactive and isolated per browser session. Runtime startup reads files into memory; it never writes to the deployed filesystem. Static assets are also in `public/assets` for Vercel's CDN.

Official hosting reference: [Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask).

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s support/tests -v
.\.venv\Scripts\python.exe -m index_engine.frozen_snapshot --check
```

The first command tests the app, including snapshot round trips and frozen callbacks. The second validates the actual snapshot that will be hosted. Unix/macOS uses `.venv/bin/python`.

For the original application's background and data requirements, see [live dashboard documentation](support/docs/live-dashboard.md) and [research methods](support/docs/holdout.md).
