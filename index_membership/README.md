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

## After the alias table (2026-11-18, backtest 297c6736861ea30d71d44efa5d5f9218)

sp500() has an alias table (later ticker -> ticker used at the time) built
from the list of unmatched members 1998-2010 (Claude's knowledge, checked
only by these match counts), and one date rule: "WM" before 2008-11-01 is
Waste Management's old ticker WMI (WM was Washington Mutual then).
Members matched: 1998 482 of 490, 2000 486 of 493, 2003 493 of 494,
2005-2006 all, 2007-2009 all but BTUUQ (Peabody). Against SPY
constituents: 2010 492 of 498, 2012 489 of 498, 2014 497 of 500, 2017 503
of 503. Still unmatched before 2005: CR, FWLT, MZIAQ, NLV, PZE, TMC.A,
WYE, EXC (1999-2000), PHA (1999), NGH, COC.B, SXCL, CE, VRTS.
