# Canadian Fear and Greed Index - RSM434

RSM434H1F Financial Trading Strategies, Fall 2026. Industry Project 2; partner: Scotiabank.

## Current scope

This is the initial **data-access checkpoint**, not the completed assignment. It contains source download scripts, an access report, and a living project README. Indicator selection, scoring, weighting, index history, evaluation, charts and trading rules have not been implemented.

The eventual research question is whether Canadian market sentiment adds useful information about future returns or risk beyond US VIX alone. Future work remains for the team to design.

Repository: [Canadian-Fear-and-Greed-Index-RSM434](https://github.com/FanDylan1234/Canadian-Fear-and-Greed-Index-RSM434) (private).

## Run the public data checks

Use Python 3.10+ for the public checker. It uses only the standard library; no API key or Node.js installation is required.

```sh
python pull_data.py
```

Optional output directory:

```sh
from pull_data import main
report = main("./my-access-results")
```

Downloads raw responses into `data-access-results/raw/` and generates `python-report.json`. Each source is handled independently: a failure does not prevent the other checks. An HTTP or parsing failure produces exit code 1; PARTIAL and NOT_TESTED entries are explicitly recorded but do not make the public-source command fail. Read the report, not just the exit code.

Checks include response status, expected schema, non-empty numeric observations, date ranges, missing values, duplicate dates and a rough calendar-day freshness flag. PASS means retrieval worked; it does not certify trading-calendar completeness or suitability. No missing values are filled and no index calculations occur.

## Run in Spyder

Download/extract the repository, keeping the files together. Open `pull_data.py` and press **F5** (Run file). Watch the **IPython Console** for live progress, PASS/PARTIAL/FAIL, observation counts, date ranges and the latest three values. The script resolves output paths relative to its own location, so Spyder's working directory need not match.

On the signed-in university Bloomberg computer, open `pull_bloomberg.py` and press F5. Install `blpapi` into the same Python environment used by Spyder. This script prints connection status, then each dataset's result. Empty ticker/field mappings are shown as NOT_CONFIGURED, never PASS. Bloomberg access still requires terminal-side verification.

Reports remain saved as JSON as well as displayed in the console. The Python public checker's live-run status is recorded in the change log below; the original historical results below came from the JavaScript checker.

## Initial results - October 22, 2026

| Required input | Source | Result |
|---|---|---|
| US VIX | FRED VIXCLS | PASS: 4,259 numeric daily observations, Jan 4, 2010-Oct 21, 2026; 124 blank observations retained in raw CSV |
| Canada 10-year benchmark yield | Bank of Canada Valet | PASS: 4,194 numeric daily observations, Jan 4, 2010-Oct 21, 2026 |
| Canadian equity options put/call ratio | Montreal Exchange CSV | PASS: 3,961 observations, Jan 4, 2011-Oct 16, 2026; last available observation is six calendar days old |
| Canadian implied volatility | Montreal Exchange VIXI chart JSON | PARTIAL: current-day intraday points download; this is not historical daily coverage |
| TSX price and total-return index | Bloomberg | NOT TESTED: needs an entitled session and confirmed security/field mappings |
| TSX advancing/declining issues and 52-week highs/lows | Bloomberg | NOT TESTED: same access requirement |
| Historical VIXC / VIXI | Bloomberg | NOT TESTED: preserve the assignment's Jan 2020-Apr 2021 transition gap |
| Canadian investment-grade corporate spreads | Bloomberg | NOT TESTED: choose and confirm a Canadian IG spread series and field |
| Bond return series for bond-versus-stock comparisons | Bloomberg | NOT TESTED: bond total-return series must be selected and confirmed |

The VIXI snapshot changes intraday; exact point count and timestamps are in the saved report. Yield levels do not substitute for bond total returns. The equity put/call CSV is preliminary exchange data and does not provide 2010 history. No fallback has been silently substituted.

## Bloomberg terminal check

The original JavaScript checker probes TCP port 8194 on localhost. During this run the port accepted a connection. **This does not authenticate Bloomberg or verify any dataset/entitlement.** No successful Bloomberg historical pull is claimed.

The optional `pull_bloomberg.py` implements daily HistoricalDataRequest pulls using Bloomberg's official `blpapi`. It was executed with Anaconda Python 3.13.5: the missing-SDK and unconfigured-mapping paths display correctly. Actual Bloomberg historical retrieval remains untested because blpapi and an entitled terminal session are required.

On the lab computer:

1. Use an entitled, signed-in Bloomberg Professional session with Desktop API access.
2. Confirm the exact security and historical field for each row in `bloomberg-series.json` using Bloomberg's security and field search. Empty mappings are intentional; guessed identifiers must not be treated as verified.
3. Install the official Python SDK according to [Bloomberg API Library](https://professional.bloomberg.com/support/api-library/).
4. Run:

```sh
python pull_bloomberg.py --start 2010-01-01
```

For a small first sample, pass explicit `--start` and `--end` dates. The script saves per-series CSVs and `bloomberg-report.json`, reports field/security errors and timeouts, and returns a nonzero exit code for unresolved datasets. API availability on university terminals must be confirmed locally.

## Files

- `pull_data.py`: preferred Python/Spyder public-source checker with live console output.
- `pull_data.mjs`: original JavaScript checker, retained for reference.
- `pull_bloomberg.py`: optional terminal-only Bloomberg historical retrieval.
- `bloomberg-series.json`: required dataset checklist; mappings await confirmation.
- `docs/initial-access-report.md` and `.json`: reproducible checkpoint evidence.
- `.gitignore`: excludes downloaded data, local environments and secrets.

## Next decisions - intentionally unfinished

- Confirm Bloomberg mappings and entitlements; retest exact histories.
- Resolve missing 2010 put/call data, Canadian volatility gaps, and stale observations.
- Agree on 5-8 indicators and their rationales.
- Later: choose past-only scoring and equal-weight baseline, freeze design through 2019, evaluate 2020 onward against VIX, then backtest one rule.

No design or empirical conclusion is implied by these future tasks.

## Course checkpoints

| Date (2026) | Milestone |
|---|---|
| Oct 25, 11:59 p.m. | Team plan and data access confirmation |
| Nov 8, 11:59 p.m. | Progress update |
| Nov 20 | Project-specific evaluation/backtest target |
| Week of Nov 23 | Dry run |
| Dec 1 | Final output |
| Week of Nov 30 | Partner presentation |
| Dec 6, 11:59 p.m. | Individual reflection |

## Sources and provenance

Assignment references supplied by the user:
- RSM434H1F-F2026-Industry Project 02 - Canadian Fear and Greed Index.pdf, pp. 1-4.
- RSM434H1F-F2026-Industry Projects - Overview.pdf, pp. 1-4.

Data and API references:
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS), source: Chicago Board Options Exchange; [CSV download](https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&cosd=2010-01-01).
- [Bank of Canada Valet documentation](https://www.bankofcanada.ca/valet/docs/); series `BD.CDN.10YR.DQ.YLD`.
- [Montreal Exchange put/call ratios](https://www.m-x.ca/en/trading/data/put-call-ratios); [equity CSV](https://www.m-x.ca/files/ratio-equity.csv).
- [Montreal Exchange homepage](https://www.m-x.ca/); its chart loads [VIXI JSON](https://www.m-x.ca/files/json/vixi.json). This is an observed website endpoint, not a promised historical API.
- [Bloomberg API Library](https://professional.bloomberg.com/support/api-library/) and [Core Developer Guide](https://data.bloomberglp.com/professional/sites/10/2017/03/BLPAPI-Core-Developer-Guide.pdf).

Keep downloaded vendor data out of Git. Confirm source usage/redistribution permissions before publishing data. Assignment PDFs are not included in the repository starter.

## AI assistance log

October 22, 2026: ChatGPT/Codex read the supplied project briefs, drafted this README and access scripts, and ran the public-source download checks. Bloomberg retrieval remains unexecuted. The team should review the code and preserve this disclosure for the course's required AI-use appendix.

## Change log

- 2026-10-22: Initial README, public-source checks, optional Bloomberg adapter, and recorded access results. Private GitHub repository created and starter files uploaded.

- 2026-10-22: Added Python/Spyder public checker and live console output to both Python scripts. Executed public checks: PASS=3, PARTIAL=1, FAIL=0. Latest equity put/call CSV now contains 3,963 observations through October 20. Original checkpoint table above remains a record of the earlier run. Bloomberg checker executed and reported missing blpapi plus ten unconfigured mappings. Spyder UI itself was not tested. Trailing NUL/whitespace padding is ignored for CSV parsing; raw responses are preserved.
