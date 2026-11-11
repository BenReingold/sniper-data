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


class SnipeRMapProbe4(QCAlgorithm):
    """Date-specific mapping: each symbol-month gets the CIK whose press
    release printed that ticker nearest in time (within 400 days)."""

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
            mcik = None
            try:
                c0 = f.company_reference.cik
                mcik = str(int(c0)) if c0 else None
            except Exception:
                pass
            r.setdefault("m", []).append((self.time.date().toordinal(), f.symbol.value, mcik))
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
        has8k = set()
        for row in csv.DictReader(io.StringIO(self.download(BASE + "8k_202.csv"))):
            has8k.add(row["cik"])
        tk = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "cik_tickers.csv"))):
            t = (row["ticker"] or "").replace(".", "")
            o = d(row["filing_date"])
            if t and o:
                tk.setdefault(t, []).append((o, row["cik"]))
        for v in tk.values():
            v.sort()

        def at(ticker, o):
            lst = tk.get(ticker.replace(".", ""))
            if not lst:
                return None
            i = bisect.bisect_left(lst, (o, ""))
            best = None
            for j in (i - 1, i):
                if 0 <= j < len(lst):
                    gap = abs(lst[j][0] - o)
                    if gap <= 400 and (best is None or gap < best[0]):
                        best = (gap, lst[j][1])
            return best[1] if best else None

        chk = {"right": 0, "wrong": 0, "no_match": 0}
        wrong_ex = []
        yrs = {}
        audit = {}
        for r in self.sec.values():
            for o, t, mc in r.get("m", []):
                y = date.fromordinal(o).year
                c = at(t, o)
                b = yrs.setdefault(y, [0, 0, 0, 0, 0])
                b[0] += 1
                ms_ok = mc is not None and mc in has8k
                if ms_ok:
                    b[1] += 1
                    if c is None:
                        chk["no_match"] += 1
                    elif c == mc:
                        chk["right"] += 1
                    else:
                        chk["wrong"] += 1
                        if len(wrong_ex) < 10:
                            wrong_ex.append(f"{t}@{date.fromordinal(o)} ms={mc} tk={c}")
                if not r["fund"]:
                    b[2] += 1
                    if c:
                        b[3] += 1
                if ms_ok or c:
                    b[4] += 1
                if t in AUDIT and y in (2005, 2007, 2008):
                    audit[(t, y)] = f"{t} {y} fund={r['fund']} ms={mc} tk={c}"
        tot = sum(chk.values())
        self.log(f"MAP4 symbol-months check vs Morningstar CIK {chk} right_share_when_matched={chk['right']/max(chk['right']+chk['wrong'],1):.3f} wrong_ex={wrong_ex}")
        self.log("MAP4 by_year symbol-months (all, ms_cik_with_8k, nofund, nofund_mapped, any_mapped) " + " ".join(f"{y}:{'/'.join(map(str, v))}" for y, v in sorted(yrs.items())))
        for k in sorted(audit):
            self.log("MAP4 audit " + audit[k])
