# sniper-data

Public data tables used by SnipeR backtests on QuantConnect.

Contents (planned):

- `earnings_dates/` — U.S. earnings announcement dates taken from SEC EDGAR
  8-K filings with item 2.02 (Results of Operations and Financial Condition),
  from August 2004. Public SEC data only.

Backtests download these files at start-up because QuantConnect project files
are limited to 32,000 characters on the free plan.
