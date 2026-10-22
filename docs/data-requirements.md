# Data definitions and required history

Source: **RSM434H1F-F2026-Industry Project 02 - Canadian Fear and Greed Index.pdf**, page 2 (Suggested Data, fallback and pipeline requirements), and pages 2-3 (design/holdout rules). **Industry Projects - Overview.pdf**, page 2, permits other documented sources and requires early confirmation of access.

The data table is suggested input data. The assignment ultimately requires at least five indicators (choose 5-8), not the use of every row. This repository audits every suggested input without selecting indicators.

| Input | Definition required by the project | Daily history requested |
|---|---|---|
| TSX price | S&P/TSX Composite price index level | 2010 to latest |
| TSX total return | S&P/TSX Composite total-return index level, including reinvested dividends | 2010 to latest |
| Advancing and declining issues | Counts of advancing/declining TSX issues | 2010 to latest |
| New highs and lows | Counts of TSX issues making new 52-week highs/lows | 2010 to latest |
| VIXC | Legacy S&P/TSX 60 implied-volatility index | October 2010 to January 2020, as available |
| VIXI | Replacement S&P/TSX 60 implied-volatility index | April 2021 to latest, as available |
| US VIX | FRED VIXCLS | 2010 to latest |
| Canadian options activity | Canadian equity options put/call ratio, Montreal Exchange | 2011 to latest |
| Canadian credit | Canadian investment-grade corporate spreads | 2010 to latest |
| Government yield | Government of Canada 10-year benchmark yield | 2010 to latest |
| Bond vs. stock returns | Bond and stock return data; bond benchmark unspecified | 2010 to latest |

The PDF does **not** supply Bloomberg tickers, field mnemonics, the breadth universe's detailed eligibility rules, an exact corporate-spread definition, or a bond total-return benchmark. These cannot be honestly marked verified merely by reading the PDF. The code therefore performs candidate/discovery tests and saves the Bloomberg metadata needed for review.

## Configured mappings and decisions awaiting review

- TSX price: `SPTSX Index / PX_LAST`. User's lab output confirmed 4,217 daily observations (2010-01-04 to 2026-10-22). Today's value is now excluded by default.
- TSX total return: try `SPTSX Index / TOT_RETURN_INDEX_GROSS_DVDS`; request Bloomberg field search and security lookup too. This is a candidate, not a claimed successful pull.
- Breadth: query Bloomberg FieldSearchRequest and instrumentListRequest. Try up to four candidate security/field pairs. Exchange-level TSX instruments and fields on the Composite are possible alternatives; **Composite-member counts must not silently stand in for all TSX exchange issues**.
- Highs/lows: counts of NEW highs/lows over 52 weeks; exclude obvious percentage/ratio/volume results. A numeric count still needs documentation review. An index's own high/low price is not breadth.
- Canadian implied volatility: try `VIXC Index / PX_LAST` and `VIXI Index / PX_LAST` separately. Legacy end is screened through 2020-01-31, using the PDF's month-level date; replacement starts 2021-04-26. The more precise VIXI launch date comes from S&P's methodology. Its published first-value date is 2017-01-04, so vendor pre-launch/back-calculated history must not erase the PDF's stated transition gap.
- Canadian IG credit: try Bloomberg's Canada Aggregate Corporate index `I05510CA Index` with candidate `INDEX_OAS_TSY_BP`, plus field search for option-adjusted spread. OAS in basis points is a proposed spread definition, not mandated by the PDF. Confirm CAD/issuer universe, IG eligibility, Treasury comparison, units and daily historical availability.
- Bond total return: try `I05486CA Index / PX_LAST`, the Bloomberg Canada Aggregate Total Return Unhedged CAD index. It includes corporate as well as government bonds. This is an explicit broad-bond candidate, not a government-only safe-haven series. The team's bond benchmark choice remains open.
- FRED VIX and Bank of Canada `BD.CDN.10YR.DQ.YLD` are public histories. A 10-year yield level is not a bond total return.

Provenance:
- [Bloomberg Canadian Indices, May 2023](https://assets.bbhub.io/professional/sites/10/Bloomberg-Canadian-Index-Monthly-May-2023.pdf), figures/tables on pages 1-2 identify the Canada Aggregate and Corporate tickers.
- [Bloomberg Canada Aggregate ESG Focus factsheet, hosted by MSCI](https://www.msci.com/documents/1296102/7825007/Bloomberg%2BBarclays%2BMSCI%2BCanadian%2BAggregate%2BESG%2BFocus%2BIndex.pdf/e7549f52-794e-938c-116a-5a97d8befa03), total-return ticker table.
- [S&P/TSX derivatives methodology](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-tsx-derivatives-indices.pdf), dissemination table for VIXI.
- [Bloomberg Core Developer Guide](https://data.bloomberglp.com/professional/sites/10/2017/03/BLPAPI-Core-Developer-Guide.pdf), field search/info and historical requests.
- [Bloomberg Developer Guide](https://data.bloomberglp.com/professional/sites/4/blpapi-developers-guide-2.54.pdf), Instruments service / Security Lookup.

## What the checker establishes

It requests daily observations, preserves missing values, screens date ranges, counts duplicates and missing weekdays, flags internal calendar gaps over 10 days, and flags identical values repeated for 10 or more observations. Counts must be nonnegative integers; index and volatility levels must be positive. These are diagnostic heuristics: holidays and legitimate repeated observations can trigger review. A complete exchange-calendar audit and independent value verification remain future work.

Default end date is yesterday in Toronto. This is conservative about unfinished sessions; late vendor publication is still possible.

`PASS` means a previously verified mapping passed the basic history screen.
`REVIEW` means numeric Bloomberg data downloaded, but definition and/or coverage still require review.
`UNRESOLVED` means search did not identify an eligible mapping.
`FAIL` means an attempted pull failed.
`BLOCKED` means the Bloomberg session/package was unavailable.
The intraday website feed is always `PARTIAL`.

Setting `verified: true` is a manual declaration after reviewing the saved Bloomberg security/field documentation; do not change it just to obtain PASS. It does not override coverage warnings.

## Gaps, backfill and holdout

- Put/call ratios start in 2011. The checker reports the unresolved 2010 gap explicitly.
- The project flags the Canadian volatility gap during 2020-21. The two Canadian series stay separate.
- The assignment allows the closest US equivalent when a Canadian series is missing, with disclosure. US VIX is downloaded as a benchmark/fallback candidate, but nothing is spliced automatically.
- Later index design must use only past data, freeze indicators/scoring/weights through 2019, and evaluate 2020 onward. A trailing 1-2 year scoring window may require extra pre-2010 warmup history or an explicit initial-window rule; this access checker does not create scoring windows.
- No returns, sentiment scores, index, holdout evaluation or backtest are computed.
