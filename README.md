# Canadian Fear and Greed Index - RSM434

RSM434H1F Financial Trading Strategies, Fall 2026. Industry Project 2; partner: Scotiabank.

This repository currently contains data retrieval and access checks. The assignment's indicator selection, sentiment index, scoring, evaluation and backtest remain unfinished.

## Run everything in Spyder

1. On GitHub, choose **Code -> Download ZIP**.
2. In Windows File Explorer, right-click the ZIP -> **Extract All**.
3. In Spyder, open **run_all_checks.py** from the extracted folder.
4. On the signed-in university Bloomberg computer, press **F5**.

Keep every extracted file together, including `bloomberg-series.json` and `data_checks.py`. Run the actual extracted script, not the ZIP or a pasted untitled copy.

Requires Python 3.10+ and Bloomberg's official `blpapi` in Spyder's Python environment. Public downloads use only Python's standard library. [Official Bloomberg SDK instructions](https://professional.bloomberg.com/support/api-library/).

Command-line equivalent:

```sh
python run_all_checks.py
```

The checker pulls the three public daily histories, checks the website VIXI snapshot, then attempts all ten Bloomberg datasets using configured candidates and Bloomberg field/security search. It prints progress, candidate mappings, dates, observations, coverage warnings and sample values as it goes.

## Required data and history

[Full PDF requirements, definitions and candidate provenance](docs/data-requirements.md).

| Input | Required daily history |
|---|---|
| S&P/TSX Composite price and total return | 2010 to latest |
| TSX advancing/declining issues; new 52-week highs/lows | 2010 to latest |
| Canadian VIXC | October 2010 to January 2020, as available |
| Replacement VIXI | April 2021 to latest, as available |
| US VIX, Canadian IG credit spreads, Canada 10-year yield, bond/stock return data | 2010 to latest |
| Canadian equity options put/call ratio | 2011 to latest |

The assignment suggests these datasets but does not provide Bloomberg identifiers. It also leaves the exact credit-spread definition and bond benchmark open. Candidate mappings are explicitly labelled; successful numeric data alone do not establish the right universe, units or series definition.

The default end date is **yesterday in Toronto**, excluding today's unfinished session. The two Canadian volatility histories stay separate. The 2010 put/call gap and 2020-21 Canadian volatility gap remain explicit.

## Console results

- `PASS`: verified mapping passed the basic date-range/quality screen.
- `REVIEW`: Bloomberg candidate downloaded, but definition or coverage needs review.
- `UNRESOLVED`: no eligible mapping found by search.
- `FAIL`: a candidate/public pull failed; other datasets continue.
- `BLOCKED`: missing SDK or inaccessible Bloomberg service.
- `PARTIAL`: VIXI website intraday snapshot; not historical daily coverage.

The checker flags late starts, early endings, long internal gaps, missing values, duplicate dates, suspicious repeated values, and non-integer/negative breadth counts. Weekday gap counts include holidays; this is not a certified exchange-calendar audit. No missing values are filled.

Bloomberg queries are bounded to four candidate pairs per dataset. A small sample is tried before full history; discovery/entitlement errors are saved. If no recent sample is available, full history is still attempted to distinguish stale data from no history. Field metadata and security names/currency are saved for definition review. The user's verified TSX price mapping is included by default.

After a Bloomberg candidate's definition has been reviewed, record its chosen `security`, `field`, and `verified: true` in `bloomberg-series.json`. Downloaded candidates remain REVIEW until then. No US fallback is silently substituted.

## Reports

All outputs go under `data-access-results/` beside the scripts:

- `all-checks-report.json` and `.md`: combined result.
- `bloomberg-report.json`: candidate attempts, errors, field/security discovery, metadata and history checks.
- `python-report.json`: public-source results.
- `raw/`: downloaded responses and per-series Bloomberg CSVs.

Downloaded vendor data are excluded from Git. Keep raw Bloomberg exports local and respect the institution's data terms. No credentials are stored in the repository.

Individual checks:

```sh
python pull_data.py
python pull_bloomberg.py
python pull_bloomberg.py --start 2010-01-01 --end 2026-10-21
```

The Bloomberg script returns nonzero in a shell if any dataset still needs review or fails. The combined script returns nonzero unless all 13 daily input checks pass; the ancillary VIXI snapshot is excluded from that count. Spyder keeps the console interactive. All checks passing does not remove the documented 2010/volatility project gaps or choose the final indicators.

## Evidence and validation

- Public Python run on October 22, 2026: FRED VIX and Canada 10-year yield from January 4, 2010 through October 21, 2026; Montreal equity put/call from January 4, 2011 through October 20, 2026 (3,963 numeric observations); VIXI snapshot PARTIAL.
- User's Bloomberg lab run: `SPTSX Index / PX_LAST` returned 4,217 observations, January 4, 2010 through October 22, 2026. This is user-provided console evidence, not an independently rerun terminal pull.
- The combined runner was executed here: public PASS=3, snapshot PARTIAL=1, Bloomberg BLOCKED=10 because this execution environment lacks `blpapi`. The user's lab already connected successfully.
- Seven offline tests passed: historical range/gaps, VIXC cessation, count validity, candidate review status, failure isolation/session cleanup, and Bloomberg response date/null/error parsing. These tests do not confirm live Bloomberg search schemas, entitlements or candidate mappings.

```sh
python -m unittest discover -s tests -v
```

Earlier access snapshots remain under `docs/initial-access-report.*`; consult run timestamps.

## Project milestones (2026)

Oct 25: team plan and data access. Nov 8: progress update. Nov 20: project evaluation/backtest target. Week of Nov 23: dry run. Dec 1: final output. Week of Nov 30: partner presentation. Dec 6: individual reflection.

## Sources and AI assistance

- User-supplied Project 2 PDF, pages 1-4; Industry Projects Overview PDF, pages 1-4.
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS), Chicago Board Options Exchange via FRED.
- [Bank of Canada Valet](https://www.bankofcanada.ca/valet/docs/), `BD.CDN.10YR.DQ.YLD`.
- [Montreal Exchange put/call ratios](https://www.m-x.ca/en/trading/data/put-call-ratios), equity CSV; [VIXI website feed](https://www.m-x.ca/files/json/vixi.json).
- Bloomberg index/API and S&P methodology references are listed in [data requirements](docs/data-requirements.md).

October 22, 2026: ChatGPT/Codex drafted the access scripts and documentation, reread both PDFs, tested public access and offline checks, and added Bloomberg candidate discovery. User independently tested the TSX price pull on the lab terminal. Remaining Bloomberg candidates need a lab run and definition review. Preserve this disclosure for the course AI-use appendix.
