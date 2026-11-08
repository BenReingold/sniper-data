from AlgorithmImports import *
import bisect
import csv
import io
import random
from datetime import date, timedelta

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/earnings_dates/"
AUDIT = {"LEH", "BSC", "MER", "WM", "WAMU", "CFC", "WB", "TWX", "YHOO", "DELL", "AAPL", "NKE"}
EXCH = {"NAS", "NYS", "NYSE", "ASE", "AMEX"}


def d(s):
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal()
    except Exception:
        return None


class SnipeRMapProbe2(QCAlgorithm):
    """Symbols without Morningstar reference data: how many, and can they be
    mapped to a CIK by matching volume spikes to 8-K item 2.02 dates?"""

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

    def spikes(self, sym, start, end):
        try:
            h = self.history(sym, start - timedelta(days=90), end + timedelta(days=5), Resolution.DAILY)
        except Exception:
            return []
        if h is None or h.empty or "volume" not in h.columns:
            return []
        v = h["volume"].droplevel(0) if h.index.nlevels > 1 else h["volume"]
        med = v.rolling(50, min_periods=20).median().shift(1)
        ratio = v / med
        out = []
        for t, x in ratio.items():
            if x == x and x >= 2.0:
                out.append(t.date().toordinal())
        return out

    def vote(self, r, by_day, dates, true_cik=None):
        """Score each candidate CIK by the share of its 8-K 2.02 filings (in the
        symbol's active range) followed by a volume spike within 0-3 days."""
        sp = self.spikes(r["sym"], r["first"], r["last"])
        if not sp:
            return None, 0, 0, 0, None
        sps = set(sp)
        cands = set()
        for s in sp:
            for back in (0, 1, 2, 3):
                cands.update(by_day.get(s - back, ()))
        lo, hi = r["first"].date().toordinal(), r["last"].date().toordinal()
        scored = []
        true_score = None
        for c in cands | ({true_cik} if true_cik else set()):
            ds = dates.get(c, [])
            inr = ds[bisect.bisect_left(ds, lo):bisect.bisect_right(ds, hi)]
            if len(inr) < 6:
                continue
            hits = sum(1 for x in inr if (x in sps or x + 1 in sps or x + 2 in sps or x + 3 in sps))
            sc = hits / len(inr)
            if c == true_cik:
                true_score = sc
            scored.append((sc, c))
        if not scored:
            return None, 0, 0, len(sp), true_score
        scored.sort(reverse=True)
        second = scored[1][0] if len(scored) > 1 else 0.0
        return scored[0][1], round(scored[0][0], 2), round(second, 2), len(sp), true_score

    def on_end_of_algorithm(self):
        dates = {}
        by_day = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "8k_202.csv"))):
            o = d(row["filing_date"])
            if o:
                dates.setdefault(row["cik"], []).append(o)
                by_day.setdefault(o, []).append(row["cik"])
        for v in dates.values():
            v.sort()

        nofund = [r for r in self.sec.values() if not r["fund"]]
        withcik = [r for r in self.sec.values() if r["cik"] and r["cik"] in dates]
        per_year = {}
        for r in self.sec.values():
            for y in r["y"]:
                b = per_year.setdefault(y, [0, 0])
                b[0] += 1
                if not r["fund"]:
                    b[1] += 1
        self.log(f"MAP2 symbols={len(self.sec)} nofund={len(nofund)} withcik_dates={len(withcik)}")
        self.log("MAP2 by_year (all, nofund) " + " ".join(f"{y}:{v[0]}/{v[1]}" for y, v in sorted(per_year.items())))

        # Calibrate the vote on symbols whose CIK is known.
        random.seed(7)
        sample = random.sample(withcik, min(200, len(withcik)))
        ok = wrong = none = 0
        ts, bo = [], []
        for r in sample:
            c, s1, s2, nsp, tsc = self.vote(r, by_day, dates, r["cik"])
            if tsc is not None:
                ts.append(tsc)
                bo.append(s2 if c == r["cik"] else s1)
            accept = c is not None and s1 >= 0.6 and s2 <= 0.4
            if not accept:
                none += 1
            elif c == r["cik"]:
                ok += 1
            else:
                wrong += 1
        self.log(f"MAP2 calib n={len(sample)} accepted_right={ok} accepted_wrong={wrong} not_accepted={none}")
        ts.sort(); bo.sort()
        qq = lambda a, p: round(a[int(p * (len(a) - 1))], 2) if a else None
        self.log(f"MAP2 calib true_score p10={qq(ts,.1)} p25={qq(ts,.25)} p50={qq(ts,.5)} | best_other p50={qq(bo,.5)} p90={qq(bo,.9)} max={qq(bo,1)}")

        # Apply to symbols without Morningstar reference data.
        res = {"accepted": 0, "rejected": 0, "nospikes": 0}
        acc_years = {}
        lines = []
        for r in nofund[:1500]:
            c, s1, s2, nsp, _ = self.vote(r, by_day, dates)
            accept = c is not None and s1 >= 0.6 and s2 <= 0.4
            if nsp == 0:
                res["nospikes"] += 1
            elif accept:
                res["accepted"] += 1
                for y in r["y"]:
                    acc_years[y] = acc_years.get(y, 0) + 1
            else:
                res["rejected"] += 1
            if r["t"] & AUDIT:
                lines.append(f"{sorted(r['t'])[:3]} {r['first'].date()}..{r['last'].date()} spikes={nsp} best={c} s1={s1} s2={s2} accept={accept}")
        self.log(f"MAP2 nofund vote {res} (of {min(len(nofund), 1500)})")
        self.log("MAP2 nofund accepted by_year " + " ".join(f"{y}:{v}" for y, v in sorted(acc_years.items())))
        for line in lines[:30]:
            self.log("MAP2 audit " + line)
        names = sorted({sorted(r["t"])[0] for r in nofund})
        self.log("MAP2 nofund sample tickers " + " ".join(names[:120]))
