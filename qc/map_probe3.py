from AlgorithmImports import *
import bisect
import csv
import io
import random
from datetime import date, timedelta

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/earnings_dates/"
AUDIT = {"LEH", "BSC", "MER", "WM", "WAMU", "CFC", "WB", "TWX", "YHOO", "DELL", "AAPL", "NKE", "AEP", "ABK", "ACS", "AA"}
EXCH = {"NAS", "NYS", "NYSE", "ASE", "AMEX"}


def d(s):
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal()
    except Exception:
        return None


class SnipeRMapProbe3(QCAlgorithm):
    """Map symbols to CIKs by the ticker printed in 8-K item 2.02 press
    releases (cik_tickers.csv), checked against Morningstar's CIK."""

    def initialize(self):
        self.set_start_date(2004, 9, 1)
        self.set_end_date(2026, 8, 10)
        self.set_cash(100000)
        self.last_month = None
        self.sec = {}
        self.add_universe(self.select)

    def select(self, fundamental):
        key = (self.time.year, self.time.month)
        if key == self.last_month:
            return Universe.UNCHANGED
        self.last_month = key
        y = self.time.year
        for f in fundamental:
            if f.price < 5 or f.dollar_volume < 5e6:
                continue
            ex = None
            try:
                ex = f.security_reference.exchange_id
            except Exception:
                pass
            if ex and ex not in EXCH:
                continue
            sid = str(f.symbol.id)
            r = self.sec.get(sid)
            if r is None:
                r = {"sym": f.symbol, "t": set(), "cik": None, "fund": False, "y": set(),
                     "first": self.time, "last": self.time}
                self.sec[sid] = r
            r["t"].add(f.symbol.value)
            r["y"].add(y)
            r["last"] = self.time
            if ex:
                r["fund"] = True
            try:
                c = f.company_reference.cik
                if c:
                    r["cik"] = str(int(c))
            except Exception:
                pass
        return []

    def on_end_of_algorithm(self):
        n8k = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "8k_202.csv"))):
            o = d(row["filing_date"])
            if o:
                n8k.setdefault(row["cik"], []).append(o)
        for v in n8k.values():
            v.sort()
        tk = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "cik_tickers.csv"))):
            t = (row["ticker"] or "").replace(".", "")
            o = d(row["filing_date"])
            if t and o:
                tk.setdefault(t, []).append((o, row["cik"]))

        def match(r):
            lo = r["first"].date().toordinal() - 400
            hi = r["last"].date().toordinal() + 400
            cands = {}
            for t in r["t"]:
                for o, c in tk.get(t.replace(".", ""), ()):
                    if lo <= o <= hi:
                        ds = n8k.get(c, [])
                        inr = bisect.bisect_right(ds, hi) - bisect.bisect_left(ds, lo)
                        cands[c] = max(cands.get(c, 0), inr)
            if not cands:
                return None, 0
            best = sorted(cands.items(), key=lambda x: -x[1])
            return best[0][0], len(cands)

        ok = wrong = miss = 0
        wrong_ex = []
        res = {"mapped": 0, "unmapped": 0, "ambiguous": 0}
        yrs = {}
        lines = []
        for r in self.sec.values():
            c, k = match(r)
            if r["fund"] and r["cik"] and r["cik"] in n8k:
                if c is None:
                    miss += 1
                elif c == r["cik"]:
                    ok += 1
                else:
                    wrong += 1
                    if len(wrong_ex) < 8:
                        wrong_ex.append(f"{sorted(r['t'])[:2]} ms={r['cik']} tk={c}")
            if not r["fund"]:
                res["mapped" if c else "unmapped"] += 1
                if k > 1:
                    res["ambiguous"] += 1
                for y in r["y"]:
                    b = yrs.setdefault(y, [0, 0])
                    b[0] += 1
                    b[1] += 1 if c else 0
            if r["t"] & AUDIT:
                lines.append(f"{sorted(r['t'])[:3]} fund={r['fund']} ms={r['cik']} {r['first'].date()}..{r['last'].date()} -> {c} (cands {k})")
        self.log(f"MAP3 check vs Morningstar CIK: right={ok} wrong={wrong} no_match={miss} wrong_ex={wrong_ex}")
        self.log(f"MAP3 nofund {res}")
        self.log("MAP3 nofund by_year (symbols, mapped) " + " ".join(f"{y}:{v[0]}/{v[1]}" for y, v in sorted(yrs.items())))
        for line in sorted(lines)[:40]:
            self.log("MAP3 audit " + line)
