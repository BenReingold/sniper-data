"""Turn the daily S&P 500 ticker lists (fja05680) into CIK membership
intervals, so that membership does not depend on which ticker a company
used at the time. A listed ticker is resolved to the CIK that printed it in
8-K item 2.02 releases (earnings_dates/cik_tickers.csv) or holds it in SEC's
current ticker list (entities.csv); if several CIKs used the ticker, the one
whose use is nearest in time to the membership interval is taken.
Output: index_membership/sp500_cik_intervals.csv  cik,ticker,start,end
        index_membership/sp500_unresolved.csv      ticker,start,end
"""
import csv
from collections import defaultdict
from datetime import date


def o(s):
    return date.fromisoformat(s).toordinal()


def norm(t):
    return t.replace(".", "").replace("-", "").upper()


uses = defaultdict(list)  # ticker -> [(ordinal, cik)]
for r in csv.DictReader(open("earnings_dates/cik_tickers.csv")):
    if r["ticker"]:
        uses[norm(r["ticker"])].append((o(r["filing_date"]), r["cik"]))
today = date.today().toordinal()
for r in csv.DictReader(open("earnings_dates/entities.csv")):
    for t in (r["tickers"] or "").split("|"):
        if t:
            uses[norm(t)].append((today, r["cik"]))

# daily lists -> per ticker intervals
rows = list(csv.DictReader(open("index_membership/sp500_daily_fja05680.csv")))
intervals = defaultdict(list)
prev = set()
start = {}
for i, r in enumerate(rows):
    cur = set(r["tickers"].split(","))
    for t in cur - prev:
        start[t] = r["date"]
    for t in prev - cur:
        intervals[t].append((start.pop(t), rows[i - 1]["date"]))
    prev = cur
for t in prev:
    intervals[t].append((start[t], ""))

out, unres = [], []
for t, ivs in intervals.items():
    for s, e in ivs:
        lo, hi = o(s), o(e) if e else today
        cands = uses.get(norm(t), [])
        if not cands:
            unres.append([t, s, e])
            continue
        def dist(x):
            return 0 if lo <= x[0] <= hi else min(abs(x[0] - lo), abs(x[0] - hi))
        best = min(cands, key=dist)
        out.append([best[1], t, s, e])
with open("index_membership/sp500_cik_intervals.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["cik", "ticker", "start", "end"]); w.writerows(sorted(out, key=lambda x: x[2]))
with open("index_membership/sp500_unresolved.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ticker", "start", "end"]); w.writerows(sorted(unres, key=lambda x: x[1]))
print(f"intervals={len(out) + len(unres)} resolved={len(out)} unresolved={len(unres)}")
# share of members resolved on sample dates
for d in ("1998-06-01", "2003-06-02", "2007-06-01", "2010-06-01", "2015-06-01"):
    od = o(d)
    tot = sum(1 for t, ivs in intervals.items() for s, e in ivs if o(s) <= od <= (o(e) if e else today))
    res = sum(1 for c, t, s, e in out if o(s) <= od <= (o(e) if e else today))
    print(d, "members", tot, "resolved", res)
