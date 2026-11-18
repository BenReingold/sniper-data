from AlgorithmImports import *
import csv
import io
from datetime import date

URL = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/index_membership/sp500_cik_intervals.csv"


def o(s):
    return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal() if s else 10 ** 7


class SnipeRD10Check2(QCAlgorithm):
    """S&P 500 membership by CIK (public history resolved to SEC CIKs)
    against QuantConnect: (1) from 2010 against SPY constituents, by CIK;
    (2) every June, how many members are found in QuantConnect's universe
    by Morningstar CIK. Examines no returns; not a trial."""

    def initialize(self):
        self.set_start_date(1998, 1, 1)
        self.set_end_date(2026, 8, 15)
        self.set_cash(100000)
        self.iv = [(r["cik"], o(r["start"]), o(r["end"])) for r in csv.DictReader(io.StringIO(self.download(URL)))]
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
        d = self.time.date().toordinal()
        members = {c for c, s, e in self.iv if s <= d <= e}
        by_cik, spy_ciks, spy_nocik = {}, set(), 0
        for f in fundamental:
            c = None
            try:
                c0 = f.company_reference.cik
                c = str(int(c0)) if c0 else None
            except Exception:
                pass
            if c:
                by_cik[c] = f.symbol
                if f.symbol in self.etf:
                    spy_ciks.add(c)
            elif f.symbol in self.etf:
                spy_nocik += 1
        found = members & set(by_cik)
        line = f"D10B {self.time.date()} members_resolved={len(members)} found_in_qc={len(found)}"
        if self.etf:
            line += (f" | spy={len(self.etf)} spy_with_cik={len(spy_ciks)} spy_no_cik={spy_nocik} both={len(spy_ciks & members)}"
                     f" only_spy={len(spy_ciks - members)} only_public={len(members - spy_ciks)}")
        self.log(line)
        return []
