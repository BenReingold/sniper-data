# S&P 500 membership history

sp500_daily_fja05680.csv: daily S&P 500 member tickers from 1996, copied
from https://github.com/fja05680/sp500 (MIT licence, LICENSE_fja05680),
commit of 2026-09-07. Per the fja05680 README, 1996-2019 is the file
distributed with Clenow's "Trading Evolved" (cleaned, duplicates removed)
and later changes come from Wikipedia (corrected 2026-11-18; this line
said "built from Wikipedia"). Tickers may be later tickers of the same
company (for example AAMRQ for AMR). Checked
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

## Check against SPDR (SPY) holdings and fix (2026-11-18)

Independent check: SEC-filed annual reports (N-30D) of SPDR Trust (SPY),
schedules of investments on 2000-09-30, 2004-09-30, 2007-09-30. The list
has no false members but loses 8, 5 and 3 members to ticker collisions (two
members of the time later share one ticker and the list keeps one: Sears and
Sprint as S, AT&T Corp and SBC as T, Allergan and Watson as AGN, Johnson
Controls and Tyco as JCI, Chubb and ACE as CB; in 2000 also AOL/Time
Warner, Chase/J.P. Morgan, First Union/Wachovia, Firstar/U.S. Bancorp).

Test qc/d10_spdr_test.py (QuantConnect project SnipeR-d10-spdr 39614419)
showed that sp500() also matched some later tickers directly to other
companies (L = Liberty Media, PTC = PAR Technology, JEF = Jefferies, ...).
Correct members before the fix: 473 of 499 (2000), 487 of 500 (2004), 492
of 500 (2007). Fix in qc/sniper_data.py: BEFORE (old ticker tried first
before a date) and COLLIDE (members the list loses, with dates; ACE and
Tyco dates from S&P Dow Jones press releases, others from Claude's
knowledge). After: 495, 499, 498 correct (remaining: Crane and Conoco
class B absent from QuantConnect's universe, Peabody 2007-2014, share
classes, one day of timing). Against QuantConnect's SPY constituents each
June: 2010 496 of 498 (was 492), 2012 493 of 498 (was 489), 2014 499 of
500 (was 497), 2015 501 of 501; no year worse. QuantConnect's SPY
constituents do not contain Tyco in 2010-2016 although S&P Dow Jones press
releases of 2012-09-24 and 2016-08-25 call it an S&P 500 constituent; the
module keeps Tyco. Details: D10_CHECK_2026-11-18.md in the SnipeR project.
