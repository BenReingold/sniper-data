from AlgorithmImports import *
from sniper_data import SniperData


class SnipeRSp500Test(QCAlgorithm):
    """sp500() of the data module against SPY constituents (from 2010) and
    share matched before 2010. Examines no returns; not a trial."""

    def initialize(self):
        self.set_start_date(1998, 1, 1)
        self.set_end_date(2026, 8, 15)
        self.set_cash(100000)
        self.sd = SniperData(self)
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
        m = self.sd.sp500(fundamental)
        line = f"SP {self.time.date()} matched={len(m)} missing={len(self.sd.sp_missing)} ex={' '.join(self.sd.sp_missing[:10])}"
        if self.etf:
            line += f" | spy={len(self.etf)} both={len(self.etf & m)} only_spy={len(self.etf - m)} only_list={len(m - self.etf)}"
        self.log(line)
        return []
