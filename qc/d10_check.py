from AlgorithmImports import *
import csv
import io

URL = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/index_membership/sp500_daily_fja05680.csv"


class SnipeRD10Check(QCAlgorithm):
    """Compares the public S&P 500 history (fja05680) with QuantConnect:
    (1) from 2010, with SPY constituents on the same day; (2) every year,
    how many listed tickers exist in QuantConnect's universe that day.
    Examines no returns; not a trial."""

    def initialize(self):
        self.set_start_date(1998, 1, 1)
        self.set_end_date(2026, 8, 15)
        self.set_cash(100000)
        self.fja = {}
        for r in csv.DictReader(io.StringIO(self.download(URL))):
            self.fja[r["date"]] = set(r["tickers"].split(","))
        self.dates = sorted(self.fja)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.etf = set()
        self.add_universe(self.universe.etf(self.spy, self.universe_settings, self.etf_sel))
        self.add_universe(self.sel)
        self.done = set()

    def etf_sel(self, constituents):
        self.etf = {c.symbol.value for c in constituents}
        return []

    def fja_on(self, d):
        import bisect
        i = bisect.bisect_right(self.dates, d) - 1
        return self.fja[self.dates[i]] if i >= 0 else set()

    def norm(self, t):
        return t.replace(".", "").replace("-", "").replace(" ", "")

    def sel(self, fundamental):
        y = self.time.year
        if self.time.month != 6 or y in self.done:
            return Universe.UNCHANGED
        self.done.add(y)
        d = self.time.strftime("%Y-%m-%d")
        f = {self.norm(t) for t in self.fja_on(d)}
        qc = {self.norm(x.symbol.value) for x in fundamental}
        inqc = f & qc
        miss = sorted(f - qc)
        line = f"D10 {d} fja={len(f)} in_qc_universe={len(inqc)} missing={len(miss)} sample_missing={' '.join(miss[:25])}"
        if self.etf:
            e = {self.norm(t) for t in self.etf}
            line += f" | spy_constituents={len(e)} both={len(e & f)} only_fja={len(f - e)} only_spy={len(e - f)} ex_only_fja={' '.join(sorted(f - e)[:8])} ex_only_spy={' '.join(sorted(e - f)[:8])}"
        self.log(line)
        return []
