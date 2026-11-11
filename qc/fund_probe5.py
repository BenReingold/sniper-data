from AlgorithmImports import *
import bisect
import csv
import io
from datetime import date

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/"
EXCH = {"NAS", "NYS", "NYSE", "ASE", "AMEX"}


def d(s):
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal()
    except Exception:
        return None


def num(x):
    try:
        v = float(x)
        return v if v == v else None
    except Exception:
        return None


class SnipeRFundProbe5(QCAlgorithm):
    """Coverage of quarterly EPS / revenue: Morningstar vs SEC XBRL tables,
    per symbol-month 2009-2026, and agreement where both exist."""

    def initialize(self):
        self.set_start_date(2009, 7, 1)
        self.set_end_date(2026, 8, 10)
        self.set_cash(100000)
        self.load()
        self.last_month = None
        self.yr = {}
        self.cmp = {"eps_n": 0, "eps_ok": 0, "rev_n": 0, "rev_ok": 0}
        self.bad = []
        self.seen_pairs = set()
        self.add_universe(self.select)

    def load(self):
        self.tk = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "earnings_dates/cik_tickers.csv"))):
            t = (row["ticker"] or "").replace(".", "")
            o = d(row["filing_date"])
            if t and o:
                self.tk.setdefault(t, []).append((o, row["cik"]))
        for v in self.tk.values():
            v.sort()
        self.q = {}
        for g in ("eps", "revenue"):
            m = {}
            for row in csv.DictReader(io.StringIO(self.download(BASE + f"fundamentals/xbrl_{g}_1.csv"))):
                s, e, f = d(row["start"]), d(row["end"]), d(row["filed"])
                v = num(row["val"])
                if s is None or e is None or f is None or v is None or not (80 <= e - s <= 100):
                    continue
                m.setdefault(row["cik"], []).append((f, e, v, row["concept"]))
            for v in m.values():
                v.sort()
            self.q[g] = m
        self.log(f"FUND5 loaded tickers={len(self.tk)} eps_ciks={len(self.q['eps'])} rev_ciks={len(self.q['revenue'])}")

    def cik_by_ticker(self, t, o):
        lst = self.tk.get(t.replace(".", ""))
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

    def latest(self, g, cik, o):
        """Latest quarter of cik filed on or before o, within 200 days."""
        lst = self.q[g].get(cik)
        if not lst:
            return None
        i = bisect.bisect_right(lst, (o, 10 ** 9, 0, "")) - 1
        if i < 0 or o - lst[i][0] > 200:
            return None
        return lst[i]

    def select(self, fundamental):
        key = (self.time.year, self.time.month)
        if key == self.last_month:
            return Universe.UNCHANGED
        self.last_month = key
        o = self.time.date().toordinal()
        y = self.time.year
        b = self.yr.setdefault(y, [0, 0, 0, 0, 0])
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
            cik = None
            try:
                c0 = f.company_reference.cik
                cik = str(int(c0)) if c0 else None
            except Exception:
                pass
            if cik is None:
                cik = self.cik_by_ticker(f.symbol.value, o)
            ms_eps = None
            try:
                ms_eps = num(f.earning_reports.diluted_eps.three_months)
            except Exception:
                pass
            xq = self.latest("eps", cik, o) if cik else None
            b[0] += 1
            b[1] += 1 if ms_eps is not None else 0
            b[2] += 1 if xq else 0
            b[3] += 1 if (ms_eps is not None or xq) else 0
            b[4] += 1 if (ms_eps is None and xq) else 0
            if ms_eps is not None and xq and y in (2012, 2016, 2020, 2024):
                pair = (cik, xq[1])
                if pair not in self.seen_pairs:
                    self.seen_pairs.add(pair)
                    self.compare(f, cik, xq, ms_eps, o)
        return []

    def compare(self, f, cik, xq, ms_eps, o):
        # only compare when Morningstar's quarter ends within 10 days of XBRL's
        try:
            pe = f.financial_statements.period_ending_date.value
            pe_o = date(pe.year, pe.month, pe.day).toordinal()
        except Exception:
            return
        if abs(pe_o - xq[1]) > 10:
            return
        x = xq[2]
        self.cmp["eps_n"] += 1
        if abs(ms_eps - x) <= max(0.011, 0.02 * abs(x)):
            self.cmp["eps_ok"] += 1
        elif len(self.bad) < 12:
            self.bad.append(f"{f.symbol.value} {date.fromordinal(xq[1])} ms={ms_eps} xbrl={x} c={xq[3]}")
        xr = self.latest("revenue", cik, o)
        try:
            ms_rev = num(f.financial_statements.income_statement.total_revenue.three_months)
        except Exception:
            ms_rev = None
        if xr and ms_rev and abs(xr[1] - xq[1]) <= 10:
            self.cmp["rev_n"] += 1
            if abs(ms_rev - xr[2]) <= 0.02 * abs(xr[2]):
                self.cmp["rev_ok"] += 1

    def on_end_of_algorithm(self):
        self.log("FUND5 by_year (symbol-months, ms_eps, xbrl_eps, either, xbrl_only) " +
                 " ".join(f"{y}:{'/'.join(map(str, v))}" for y, v in sorted(self.yr.items())))
        c = self.cmp
        self.log(f"FUND5 agreement eps {c['eps_ok']}/{c['eps_n']} rev {c['rev_ok']}/{c['rev_n']}")
        for line in self.bad:
            self.log("FUND5 eps_diff " + line)
