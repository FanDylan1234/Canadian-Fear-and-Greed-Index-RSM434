# Data access check

Tested: 2026-10-22T16:41:15.431Z

| Dataset | Status | Numeric rows | First observation | Last observation |
|---|---|---:|---|---|
| fred_vix | PASS | 4259 | 2010-01-04 | 2026-10-21 |
| boc_canada_10y | PASS | 4194 | 2010-01-04 | 2026-10-21 |
| mx_equity_put_call | PASS | 3961 | 2011-01-04 | 2026-10-16 |
| mx_vixi_snapshot | PARTIAL | 370 | 2026-10-22T13:35:00.000Z | 2026-10-22T16:39:30.000Z |
| bloomberg_tsx_price | NOT_TESTED |  |  |  |
| bloomberg_tsx_total_return | NOT_TESTED |  |  |  |
| bloomberg_tsx_advancing_declining | NOT_TESTED |  |  |  |
| bloomberg_tsx_52week_highs_lows | NOT_TESTED |  |  |  |
| bloomberg_canada_vixc_vixi_history | NOT_TESTED |  |  |  |
| bloomberg_canada_ig_credit_spreads | NOT_TESTED |  |  |  |
| bloomberg_canada_bond_total_return | NOT_TESTED |  |  |  |

- **fred_vix**: US VIX benchmark / explicitly labelled possible fallback, not Canadian volatility.
- **boc_canada_10y**: Government of Canada benchmark yield; a yield series is NOT a bond total-return series.
- **mx_equity_put_call**: Equity options only. Source begins in 2011; no 2010 observations are invented.
- **mx_vixi_snapshot**: Public chart feed only. Does not establish historical daily VIXI/VIXC access or fill the 2020-21 gap.
- **bloomberg_tsx_price**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.
- **bloomberg_tsx_total_return**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.
- **bloomberg_tsx_advancing_declining**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.
- **bloomberg_tsx_52week_highs_lows**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.
- **bloomberg_canada_vixc_vixi_history**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.
- **bloomberg_canada_ig_credit_spreads**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.
- **bloomberg_canada_bond_total_return**: Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.

Bloomberg TCP probe: TCP port open; Bloomberg identity and entitlements NOT verified

PASS means a non-empty numeric payload was downloaded and parsed. It does not certify completeness, licensing, accuracy, or trading-calendar coverage.
Missing observations are preserved. No forward fill, returns, indicator selection, or index construction is performed.
