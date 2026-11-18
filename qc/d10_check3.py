from AlgorithmImports import *
import bisect
import csv
import io
from datetime import date

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/index_membership/"


def o(s):
    return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal() if s else 10 ** 7


def norm(t):
    return t.replace(".", "").replace("-", "").replace(" ", "").upper()


class SnipeRD10Check3(QCAlgorithm):
    """Hybrid S&P 500 membership: each listed ticker is matched to the
    QuantConnect symbol with that ticker on the day; if none, through its
    CIK (sp500_cik_intervals.csv) to the symbol with that Morningstar CIK.
    Compared with SPY constituents from 2010 (by symbol); before 2010 the
    share of members found is reported. Examines no returns; not a trial."""

    def initialize(self):
        self.set_start_date(1998, 1, 1)
        self.set_end_date(2026, 8, 15)
        self.set_cash(100000)
        rows = list(csv.DictReader(io.StringIO(self.download(BASE + "sp500_daily_fja05680.csv"))))
        self.dates = [r["date"] for r in rows]
        self.lists = [r["tickers"].split(",") for r in rows]
        self.tcik = {}
        for r in csv.DictReader(io.StringIO(self.download(BASE + "sp500_cik_intervals.csv"))):
            self.tcik.setdefault(norm(r["ticker"]), []).append((o(r["start"]), o(r["end"]), r["cik"]))
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.etf = set()
        self.add_universe(self.universe.etf(self.spy, self.universe_settings, self.etf_sel))
        self.add_universe(self.sel)
        self.done = set()

    def etf_sel(self, constituents):
        self.etf = {c.symbol for c in constituents}
        return []

    def sel(self, fundamental):
        y = self.time.year
        if self.time.month != 6 or y in self.done:
            return Universe.UNCHANGED
        self.done.add(y)
        d = self.time.strftime("%Y-%m-%d")
        od = self.time.date().toordinal()
        i = bisect.bisect_right(self.dates, d) - 1
        tickers = self.lists[i] if i >= 0 else []
        by_t, by_c = {}, {}
        for f in fundamental:
            by_t.setdefault(norm(f.symbol.value), f.symbol)
            try:
                c0 = f.company_reference.cik
                if c0:
                    by_c[str(int(c0))] = f.symbol
            except Exception:
                pass
        mapped, via_t, via_c, miss = set(), 0, 0, []
        for t in tickers:
            s = by_t.get(norm(t))
            if s is not None:
                via_t += 1
            else:
                for a, b, c in self.tcik.get(norm(t), []):
                    if a - 5 <= od <= b + 5 and c in by_c:
                        s = by_c[c]
                        via_c += 1
                        break
            if s is None:
                miss.append(t)
            else:
                mapped.add(s)
        line = f"D10C {d} listed={len(tickers)} by_ticker={via_t} by_cik={via_c} missing={len(miss)} ex={' '.join(miss[:12])}"
        if self.etf:
            line += f" | spy={len(self.etf)} both={len(self.etf & mapped)} only_spy={len(self.etf - mapped)} only_public={len(mapped - self.etf)}"
        self.log(line)
        return []
