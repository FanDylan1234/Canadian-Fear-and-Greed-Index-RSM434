# Canadian Fear and Greed Index
RSM434 Financial Trading Strategies Â· University of Toronto Â· Scotiabank industry project

## Start here
Keep the extracted project folder together. Open it in VS Code and run this command in a PowerShell terminal:

```powershell
python start.py
```

Open http://127.0.0.1:8050 and keep the terminal open. Python 3.10â€“3.13 is supported. Python 3.12 is recommended.
The launcher finds a supported interpreter, creates a local .venv, and installs the required package versions there.
This is the only script you need to run. The dashboard refreshes sources and builds the index when it starts. Use **Refresh data** to request another refresh.

In VS Code, select **Python: Select Interpreter**, then choose **.venv/Scripts/python.exe**.
Package installation and execution must use the same interpreter. Packages installed in Anaconda are separate from Python 3.14.
The **fgindex** folder contains the project code. Keep it beside **start.py**.

## Optional commands
| Task | PowerShell command |
|---|---|
| Use cached data | `python start.py --offline` |
| Refresh data and build outputs | `python start.py --update --refresh` |
| Rebuild from cached data | `python start.py --update` |
| Diagnose data access | `python start.py --check-data` |
| Replace older breadth exports | `python start.py --repair-breadth` |
| Run validation tests after setup | `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` |

The first setup needs internet access to install packages, including when --offline is selected.
If setup fails, the terminal shows the installation error. Rerun after resolving it.
An unusable existing .venv can be renamed so setup creates a fresh one.

## Bloomberg and source data
Sign into Bloomberg Terminal on the lab workstation. Install Bloomberg's official blpapi SDK into **.venv/Scripts/python.exe** using the institution's SDK instructions.
It is a separate vendor dependency. The dashboard can open without it, but Bloomberg refreshes require it.
A fresh download has no market history. Refresh on the Bloomberg workstation to populate data-access-results/raw.

Daily observations end at yesterday in Toronto. Quotes update separately. Failed refreshes retain cached inputs.
Some source definitions still need review. Consult the Data & weights page before interpreting the index.

## What each part does
| File or folder | Purpose |
|---|---|
| start.py | Finds Python, installs packages, and launches the chosen task |
| fgindex/ | Dashboard, index calculations, data downloads, and diagnostics |
| index-config.json | Scoring windows and publication rules |
| bloomberg-series.json | Bloomberg securities, fields, and verification flags |
| requirements.txt | Required Python packages and allowed versions |
| assets/ | Dashboard appearance |
| tests/ | Automated checks for calculation and data-access behavior |
| docs/ | Source requirements and earlier research checkpoints |
| .vscode/ | Editor settings and the F5 launch shortcut |

Read the calculation in **fgindex/model.py**, then **fgindex/data.py** and **fgindex/pipeline.py**.
**fgindex/charts.py** draws charts, **fgindex/live.py** retrieves data, and **fgindex/service.py** schedules refreshes.

Generated folders are excluded from Git. **.venv** holds installed packages, **data-access-results** holds downloads, and **index-results** holds index CSVs and charts.
Keep downloaded inputs if you need offline use. Outputs can be rebuilt from those inputs.

## Methodology
Seven signals measure momentum, new highs minus lows, advancing/declining breadth, put/call, volatility, credit spreads, and stock-minus-bond total returns.
Each is ranked against up to 252 prior TSX sessions, with 126 finite observations required. Higher scores mean greater greed.
Available components have equal weights. At least five are required to publish. Missing observations remain missing.
Canadian volatility series are ranked separately, with a labelled US VIX fallback. Composite breadth excludes legacy Venture exports.
History begins in 2010 where sufficient warmup exists. The timeline is a research index. Predictive evaluation and trading tests remain future work.

See [source requirements](docs/data-requirements.md) and [earlier development notes](docs/development-history.md) for detailed evidence, milestones, and AI-use disclosure.


## US VIX refresh and tab rendering
FRED is attempted with a 10-second timeout. If it fails or returns invalid history, the dashboard downloads official [Cboe daily VIX closes](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv). This is US VIX, not a replacement Canadian volatility index. The legacy `fred_vix.csv` filename is retained for compatibility; `us-vix-source.json` records the actual distributor, URL, dates and checksum, and Data & weights shows the matching source. A download that loses cached observations, contains invalid values, or is over seven calendar days behind the requested end is rejected. If both providers fail, the cache is unchanged and the warning includes its last date.

Each tab now mounts a keyed page with distinct graph IDs. A browser-side visibility guard hides the previous page immediately on navigation while the server prepares the next page.
