# Canadian Fear and Greed Index
RSM434 Financial Trading Strategies University of Toronto & Scotiabank industry project

## Start here
Keep the extracted project folder together. Open it in VS Code and run this command in a PowerShell terminal:

```powershell
python runtostartindex.py
```

Open http://127.0.0.1:8050 and keep the terminal open. Python 3.10-3.13 is supported. Python 3.12 is recommended.
The launcher finds a supported interpreter, creates a local .venv, and installs the required package versions there.
This is the only script you need to run. The dashboard refreshes sources and builds the index when it starts. Use **Refresh data** to request another refresh.

For the configured F5 shortcut, open **support/Canadian-Fear-and-Greed.code-workspace** in VS Code. It opens the repository root and loads the launch settings. The relocated support/.vscode files are reference templates; VS Code does not discover them automatically.

In VS Code, select **Python: Select Interpreter**, then choose **.venv/Scripts/python.exe**.
Package installation and execution must use the same interpreter. Packages installed in Anaconda are separate from Python 3.14.
The **index_engine** folder contains the project code. Keep it beside **runtostartindex.py**.

## Optional commands
| Task | PowerShell command |
|---|---|
| Use cached data | `python runtostartindex.py --offline` |
| Refresh data and build outputs | `python runtostartindex.py --update --refresh` |
| Rebuild from cached data | `python runtostartindex.py --update` |
| Diagnose data access | `python runtostartindex.py --check-data` |
| Replace older breadth exports | `python runtostartindex.py --repair-breadth` |
| Run validation tests after setup | `.\.venv\Scripts\python.exe -m unittest discover -s support/tests -v` |

The first setup needs internet access to install packages, including when --offline is selected.
If setup fails, the terminal shows the installation error. Rerun after resolving it.
An unusable existing .venv can be renamed so setup creates a fresh one.

## Bloomberg and source data
Sign into Bloomberg Terminal on the lab workstation. Install Bloomberg's official blpapi SDK into **.venv/Scripts/python.exe** using the institution's SDK instructions.
It is a separate vendor dependency. The dashboard can open without it, but Bloomberg refreshes require it.
Each checkout creates its own data-access-results/raw folder at startup and reuses it on later runs. Online startup requests source histories automatically. Offline mode uses previously downloaded files. A first run needs successful source requests to populate the cache.

Daily observations end at yesterday in Toronto. Quotes update separately. Failed refreshes retain cached inputs.
Data & weights shows source coverage and exclusions. The audit manifest preserves the instrument, field and verification metadata for each source.

## What each part does
| File or folder | Purpose |
|---|---|
| runtostartindex.py | Finds Python, installs packages, and launches the chosen task |
| index_engine/ | Dashboard, index calculations, data downloads, and diagnostics |
| support/config/index-config.json | Scoring windows and publication rules |
| support/config/bloomberg-series.json | Bloomberg securities, fields, and verification flags |
| support/requirements.txt | Required Python packages and allowed versions |
| support/assets/ | Dashboard appearance |
| support/tests/ | Automated checks for calculation and data-access behavior |
| support/docs/ | Source requirements and earlier research checkpoints |
| support/.vscode/ | Editor configuration templates |
| support/Canadian-Fear-and-Greed.code-workspace | Open in VS Code to use workspace settings and F5 |

Read the calculation in **index_engine/buildindicatorsfromdata.py**, then **index_engine/loadpulleddata.py** and **index_engine/pipeline.py**.
**index_engine/chartsdesign.py** draws charts, **index_engine/liverefresh.py** retrieves data, and **index_engine/service.py** schedules refreshes.

Generated folders are excluded from Git. **.venv** holds installed packages, **data-access-results** holds downloads, and **index-results** holds index CSVs and charts.
Keep downloaded inputs if you need offline use. Outputs can be rebuilt from those inputs.

## Methodology
Seven signals measure momentum, new highs minus lows, advancing/declining breadth, put/call, volatility, credit spreads, and stock-minus-bond total returns.
Each is ranked against up to 252 prior TSX sessions, with 126 finite observations required. Higher scores mean greater greed.
Available components have equal weights. At least five are required to publish. Missing observations remain missing.
Canadian volatility series are ranked separately. When neither can be scored, the volatility indicator is left out and the others share its weight; US VIX is used only as a comparison benchmark. Composite breadth excludes legacy Venture exports.
History begins in 2010 where sufficient warmup exists. **Prediction**, **Episodes**, **US VIX comparison**, and **Backtest** cover the holdout from 2020 onward. The update command also writes **index-results/holdout-audit.zip**. Download it from any research tab for the dated inputs, forecasts, trading ledger, calibration, and checksums. The [holdout methods and audit guide](support/docs/holdout.md) explains how to reproduce a result.

See [source requirements](support/docs/data-requirements.md) and [earlier development notes](support/docs/development-history.md) for detailed evidence, milestones, and AI-use disclosure.


## US VIX refresh and tab rendering
FRED is attempted with a 10-second timeout. If it fails or returns invalid history, the dashboard downloads official [Cboe daily VIX closes](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv). This is US VIX, not a replacement Canadian volatility index. The legacy `fred_vix.csv` filename is retained for compatibility; `us-vix-source.json` records the actual distributor, URL, dates and checksum, and Data & weights shows the matching source. A download that loses cached observations, contains invalid values, or is over seven calendar days behind the requested end is rejected. If both providers fail, the cache is unchanged and the warning includes its last date.

Each tab now mounts a keyed page with distinct graph IDs. A browser-side visibility guard hides the previous page immediately on navigation while the server prepares the next page.

Put/call publication delays: the most recent valid calculated options score is carried forward into equal weighting. Raw ratios remain unfilled. The banner, options card, selected-date weights and exported `options_score_date` / `options_carried_forward` fields identify older observations. There is no carry before the first valid score; later observations never fill earlier dates. Historical values reflect this policy and may differ from earlier exports.

## Repository layout
The root keeps the launcher, README and repository-wide .gitignore. Python implementation lives in index_engine/. Supporting configuration, assets, documentation, tests and editor setup live in support/. The launcher reads support/requirements.txt. A reference copy of ignore rules is in support/.gitignore; Git requires the active repository-wide rules at the root.
