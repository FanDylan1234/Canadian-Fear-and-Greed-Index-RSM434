# Holdout evaluation and audit guide

The seven-indicator baseline uses the existing prior-session percentile ranks, Canadian-only volatility sources, options carry policy, and equal weights among at least five available components. The research settings are fixed in `index_engine/holdout.py`. A custom live configuration triggers a separate calculation with the baseline parameters. The exercise is retrospective. Its source files contain historical revisions, and the volatility replacement reflects the recorded VIXC/VIXI transition. There is no archived record of the design being specified in 2019 or of when every observation became available.

## Reproduce a result

Run `python runtostartindex.py --update` with the project's cached inputs. Open `index-results/holdout-audit.zip`. Keep the archive to preserve that build when later refreshes replace the local data. In the dashboard, each research tab has a link to the complete archive.

| File in the archive | How to use it |
|---|---|
| manifest.json | Build timestamp, active configuration, raw-file SHA-256 hashes, actual Bloomberg securities and fields, VIX distributor when verified, coverage flags, calibration checksum and calculation file hashes. Raw hashes refer to the original bytes in data-access-results/raw. |
| calibration.json | Research configuration, ordered components, training fingerprint, Methodology score bands and 2010–2019 mean forecasts and counts for each sentiment and horizon. This is the exact calibration used for this build. |
| source-levels.csv | Parsed, validated source fields aligned to observed TSX price dates, including pre-2010 scoring warmup. Column names correspond to local source filenames. Excluded definitions and missing observations stay blank. |
| observations.csv | One row per TSX close. Includes training/holdout flag, index, seven scores and weights, options source date, volatility source, VIX level and score, return benchmarks, sentiment groups, actual outcomes, end dates and holdout forecasts. |
| predictions.csv | Holdout sample counts, mean TSX total return and mean annualized volatility by index sentiment and horizon. |
| episodes.csv | Date windows, scored and extreme-fear counts, first breach, minimum and first date at the minimum. |
| vix-comparison.csv | Paired counts and forecast RMSE for each target and horizon. Advantage equals VIX RMSE minus Canadian-index RMSE. The index_closer_days column counts individual dates where the Canadian forecast had a smaller absolute error. |
| backtest-ledger.csv | One row per joint close, with signal date, score and regime, equity weights during the preceding interval and after execution, allocation changes, asset returns, turnover, costs and wealth paths for the sentiment strategy, the 60/40 benchmark and both single assets. |
| backtest-performance.csv | Ending wealth, cumulative and annualized return, annualized volatility, Sharpe ratio and maximum drawdown for the sentiment strategy before and after costs, the 60/40 benchmark, and TSX and Canada Aggregate buy and hold. |

## Signals, outcomes and comparison

Trading sessions are observed TSX price dates. Both signals use the exact Methodology score bands, classified before display rounding:

| Sentiment | Score |
|---|---|
| Extreme fear | 0 ≤ score < 25 |
| Fear | 25 ≤ score < 45 |
| Neutral | 45 ≤ score ≤ 55 |
| Greed | 55 < score ≤ 75 |
| Extreme greed | 75 < score ≤ 100 |

These are score intervals, not equal-sized samples. US VIX is independently scored as 100 minus its prior-window percentile, so high raw VIX tends toward fear. The bands apply to that score, not to the raw VIX level.

Forecast training uses the intersection of available Canadian-index and VIX dates for each horizon and the same TSX outcome. The calibration calculation ends the training history on December 31, 2019 **before** constructing forward labels. Only outcomes fully completed by that date contribute. For each signal, group and horizon, the forecast is that group's historical mean. An empty training group has no forecast, never a zero forecast. Neither the group means nor the score intervals are tuned using 2020-onward outcomes.

Each build recalculates the means from its local pre-2020 history and includes them in `calibration.json` in the archive. Source revisions can change those means. This replaces the former saved quintile calibration, which is incompatible with score-based groups. The manifest records the actual calibration checksum and training fingerprint; preserve the archive to reproduce a particular build.

To independently check a build against the same local inputs:

```python
import json
from zipfile import ZipFile
from index_engine.holdout import BASELINE, CUTOFF, build_index, fit_calibration
from index_engine.loadpulleddata import ROOT, read_inputs

inputs, _ = read_inputs(ROOT / "data-access-results/raw", BASELINE)
trained = fit_calibration(build_index(inputs.loc[:CUTOFF], BASELINE).history)
with ZipFile(ROOT / "index-results/holdout-audit.zip") as archive:
    saved = json.loads(archive.read("calibration.json"))
print(trained["train_sha256"], trained["models"] == saved["models"])
```

For a prediction row, select `period=holdout` and the chosen `index_sentiment` in observations.csv. A 1-, 3-, or 6-month horizon uses 21, 63, or 126 TSX sessions. For example, `return_1m` equals the TSX gross total-return level on `end_1m` divided by the signal-date level, less one. For `vol_1m`, take the 21 successive daily simple returns ending on that date, compute their sample standard deviation (ddof=1), and multiply by the square root of 252. A missing level in the path or an unfinished horizon leaves both outcomes blank. Average the nonblank outcomes and count the corresponding starting dates. All return, volatility, cost and error fields are decimals. Multiply by 100 to read them as percentages or percentage-point differences.

Prediction describes observed 2020-onward averages. The hypothesis is that Extreme fear precedes higher average returns than Fear, then Neutral, Greed and Extreme greed. The dashboard reports whether this ordering holds at each horizon; it does not impose the ordering on either observed results or forecasts.

For a comparison row, keep the dates with an observed outcome and both forecasts. For each signal take the square root of the mean squared forecast-minus-actual difference. Compare these errors on the identical dates. Success means lower holdout RMSE. A +5% forecast followed by +2% actual return misses by 3 percentage points. If all misses were that size, RMSE would be 3 pp. RMSE is not an investment return or a win rate. Return and volatility forecasts are evaluated separately. Daily forward windows overlap. Counts describe observations and the analysis makes no statistical significance claim. The Canadian index contains no US VIX data: when no Canadian volatility score exists, that component is excluded and the others are reweighted equally.

For an episode, select March 1–31, 2020 or January 1–December 31, 2022 in observations.csv. Count scores strictly below 25 and divide by the count of valid scores. Read the first qualifying date and the first occurrence of the minimum directly from those rows.

## Trading convention

Bloomberg's TOT_RETURN_INDEX_GROSS_DVDS field uses a base tied to the requested start date. Refreshes request the complete TSX total-return path from the configured history start and replace it as one series. For legacy caches, the loader checks the ratio of total-return to price levels between common closes at most ten calendar days apart. A change above 5% in absolute value flags a scale break. From that date the loader withholds total-return levels until a consistent history is available. The audit manifest records the break or the fixed request start when available.

Both portfolios start with CAD 100 split 60/40 between TSX equities and Canada Aggregate bonds at the first joint total-return close of 2020 or later. The sentiment strategy targets 100% equities after an Extreme fear score (below 25), 100% bonds after an Extreme greed score (above 75), and 60/40 after any other score. A missing score keeps the last target. The benchmark always targets 60/40. Only a strictly earlier close can determine a trade. If an asset level is missing, the latest score before the next joint close governs execution.

At each joint close, each portfolio first earns its prior mix's return over the interval, then rebalances from the drifted weights to its target. Trading costs 10 basis points of the value moved between the two assets (5 per leg), so a full switch costs 10 basis points of the portfolio. Daily rebalancing of the 60/40 benchmark incurs only small drift costs. Both portfolios end marked to market.

Annualized return uses actual elapsed calendar days divided by 365.2425. Annualized volatility is the sample standard deviation of daily returns multiplied by the square root of 252. The Sharpe ratio divides the annualized mean daily return (mean times 252) by annualized volatility, with a 0% risk-free rate because no cash-rate series is loaded. Maximum drawdown is the worst percentage fall from an earlier portfolio high on the joint-close path. The ledger can understate intra-period losses when a mark is missing. Taxes, product fees, tracking differences, variable spreads and actual release delays are outside the simulation.

The source mapping for the Canadian bond benchmark is documented in the [Bloomberg Canada Aggregate factsheet](https://assets.bbhub.io/professional/sites/27/Canada-Aggregate-Index.pdf). US VIX comes from the pipeline's cached FRED or Cboe daily closes. [Cboe historical data](https://www.cboe.com/tradable_products/vix/vix_historical_data/)
