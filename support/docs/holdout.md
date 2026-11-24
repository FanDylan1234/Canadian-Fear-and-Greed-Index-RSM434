# Holdout evaluation and audit guide

The seven-indicator baseline uses the existing prior-session percentile ranks, source priorities, options carry policy, and equal weights among at least five available components. The research settings are fixed in `index_engine/holdout.py`. A custom live configuration triggers a separate calculation with the frozen parameters. The exercise is retrospective. Its source files contain historical revisions, and the volatility replacement reflects the recorded VIXC/VIXI transition. There is no archived record of the design being specified in 2019 or of when every observation became available.

## Reproduce a result

Run `python runtostartindex.py --update` with the project's cached inputs. Open `index-results/holdout-audit.zip`. Keep the archive to preserve that build when later refreshes replace the local data. In the dashboard, each research tab has a link to the complete archive.

| File in the archive | How to use it |
|---|---|
| manifest.json | Build timestamp, active configuration, raw-file SHA-256 hashes, actual Bloomberg securities and fields, VIX distributor when verified, coverage flags, frozen calibration checksum and calculation file hashes. Raw hashes refer to the original bytes in data-access-results/raw. |
| calibration.json | Frozen research configuration, ordered components, training fingerprint, four score cutoffs per signal and 2010–2019 mean forecasts and counts for each quintile and horizon. The tracked original is support/config/holdout-calibration.json. |
| source-levels.csv | Parsed, validated source fields aligned to observed TSX price dates, including pre-2010 scoring warmup. Column names correspond to local source filenames. Excluded definitions and missing observations stay blank. |
| observations.csv | One row per TSX close. Includes training/holdout flag, index, seven scores and weights, options source date, volatility source, VIX level and score, return benchmarks, quintiles, actual outcomes, end dates and holdout forecasts. |
| predictions.csv | Holdout sample counts, mean TSX total return and mean annualized volatility by index quintile and horizon. |
| episodes.csv | Date windows, scored and extreme-fear counts, first breach, minimum and first date at the minimum. |
| vix-comparison.csv | Paired counts and forecast RMSE for each target and horizon. Advantage equals VIX RMSE minus Canadian-index RMSE. |
| backtest-ledger.csv | One row per joint close, with signal date and score, holdings during the preceding interval and after execution, switches, asset returns, costs and wealth paths. |
| backtest-performance.csv | Ending wealth, cumulative and annualized return, and maximum drawdown for the rule before/after costs and both passive benchmarks. |

## Signals, outcomes and comparison

Trading sessions are observed TSX price dates. Each signal's four quintile boundaries are linearly interpolated 20th, 40th, 60th and 80th percentiles of its available 2010–2019 scores. Boundary ties go to the lower quintile. US VIX is independently scored as 100 minus its prior-window percentile. Forecast training uses the intersection of available index and VIX dates for each horizon and the same TSX outcome. The calibration calculation takes a history ending December 31, 2019 before it constructs forward labels. A normal rebuild reads the saved calibration and never fits to new data. The manifest reports if today's training inputs differ from the frozen fingerprint.

To independently rebuild the calibration with the installed project interpreter, run the following at the repository root. This prints the derived settings and compares the cutoffs and forecasts with the saved file.

```python
import json
from index_engine.holdout import BASELINE, CUTOFF, CALIBRATION_FILE, build_index, fit_calibration
from index_engine.loadpulleddata import ROOT, read_inputs

inputs, _ = read_inputs(ROOT / "data-access-results/raw", BASELINE)
trained = fit_calibration(build_index(inputs.loc[:CUTOFF], BASELINE).history)
saved = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
print(trained["train_sha256"], trained["models"] == saved["models"])
```

For a prediction row, select `period=holdout` and the chosen `index_quintile` in observations.csv. A 1-, 3-, or 6-month horizon uses 21, 63, or 126 TSX sessions. For example, `return_1m` equals the TSX gross total-return level on `end_1m` divided by the signal-date level, less one. For `vol_1m`, take the 21 successive daily simple returns ending on that date, compute their sample standard deviation (ddof=1), and multiply by the square root of 252. A missing level in the path or an unfinished horizon leaves both outcomes blank. Average the nonblank outcomes and count the corresponding starting dates. All return, volatility, cost and error fields are decimals. Multiply by 100 to read them as percentages or percentage-point differences.

For a comparison row, keep the dates with an observed outcome and both forecasts. For each signal take the square root of the mean squared forecast-minus-actual difference. Compare these errors on the identical dates. Success means lower holdout RMSE. Daily forward windows overlap. Counts describe observations and the analysis makes no statistical significance claim. The Canadian index sometimes uses US VIX as a fallback component.

For an episode, select March 1–31, 2020 or January 1–December 31, 2022 in observations.csv. Count scores strictly below 25 and divide by the count of valid scores. Read the first qualifying date and the first occurrence of the minimum directly from those rows.

## Trading convention

Start with CAD 100 already invested in equities at the first joint TSX and Canada Aggregate total-return close of 2020 or later. Scores below 25 target equities. Scores above 75 target bonds. All other readings, including missing scores, keep the last instruction. Only a strictly earlier close can determine a trade. If an asset level is missing, the latest extreme signal before the next joint close governs execution. The prior holding earns the full return between the two joint closes. A switch costs 10 basis points of the marked portfolio across both legs (assumed 5 each). The strategy ends marked to market.

For each row after inception, multiply prior net wealth by one plus the return of the holding during the interval, then by one minus the cost fraction. The passive benchmarks use the same dates, reinvest distributions and incur no switching costs. Annualized return uses actual elapsed calendar days divided by 365.2425. Maximum drawdown is the worst percentage fall from an earlier portfolio high on the joint-close path. The ledger can understate intra-period losses when a mark is missing. Taxes, product fees, tracking differences, variable spreads and actual release delays are outside the simulation.

The source mapping for the Canadian bond benchmark is documented in the [Bloomberg Canada Aggregate factsheet](https://assets.bbhub.io/professional/sites/27/Canada-Aggregate-Index.pdf). US VIX comes from the pipeline's cached FRED or Cboe daily closes. [Cboe historical data](https://www.cboe.com/tradable_products/vix/vix_historical_data/)
