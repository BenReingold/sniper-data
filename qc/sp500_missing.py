from AlgorithmImports import *
from sniper_data import SniperData


class SnipeRSp500Missing(QCAlgorithm):
    """Lists every S&P 500 ticker of the public list that sp500() cannot
    match, with the first and last month it was missed. Not a trial."""

    def initialize(self):
        self.set_start_date(1998, 1, 1)
        self.set_end_date(2010, 12, 31)
        self.set_cash(100000)
        self.sd = SniperData(self)
        self.add_universe(self.sel)
        self.last = None
        self.miss = {}

    def sel(self, fundamental):
        m = (self.time.year, self.time.month)
        if m == self.last:
            return Universe.UNCHANGED
        self.last = m
        self.sd.sp500(fundamental)
        d = str(self.time.date())[:7]
        for t in self.sd.sp_missing:
            a = self.miss.setdefault(t, [d, d])
            a[1] = d
        return []

    def on_end_of_algorithm(self):
        items = sorted(self.miss.items(), key=lambda x: x[1][0])
        chunk = []
        for t, (a, b) in items:
            chunk.append(f"{t}:{a}:{b}")
            if len(chunk) == 25:
                self.log("MISS " + " ".join(chunk))
                chunk = []
        if chunk:
            self.log("MISS " + " ".join(chunk))
        self.log(f"MISS total={len(items)}")
