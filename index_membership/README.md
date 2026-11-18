# S&P 500 membership history

sp500_daily_fja05680.csv: daily S&P 500 member tickers from 1996, copied
from https://github.com/fja05680/sp500 (MIT licence, LICENSE_fja05680),
commit of 2026-09-07. Built from Wikipedia change lists; tickers may be
later tickers of the same company (for example AAMRQ for AMR). Checked
against QuantConnect's SPY constituents in qc/d10_check.py before use.

## Module function sp500() (qc/sniper_data.py), test 2026-11-18

Backtest fb623ac0bcc8eff8b6741bd483e3d1a9 (project SnipeR-data). Members
matched to a QuantConnect symbol: 1998 445 of 490, 2003 473 of 494,
2007 476 of 497, 2009 484 of 499. Against SPY constituents: 2010 479 of
498. Still missed: companies listed under a later name or OTC ticker
(ARNC = old Alcoa AA, BHGE = Baker Hughes BHI, ANDV = Tesoro TSO, DXC =
Computer Sciences CSC, MSI = Motorola MOT, NEE = FPL, EKDKQ = Kodak EK,
ABKFQ = Ambac ABK, CCTYQ = Circuit City CC); fixing them needs a dated
alias table.
