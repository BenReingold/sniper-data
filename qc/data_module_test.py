from AlgorithmImports import *
from sniper_data import SniperData
import time


class SnipeRDataModuleTest(QCAlgorithm):
    """Runs the data module over a period and logs the coverage report,
    plus spot checks. Examines no returns; not a trial."""

    def initialize(self):
        self.set_start_date(2006, 1, 1)
        self.set_end_date(2008, 12, 31)
        self.set_cash(100000)
        self.t0 = time.time()
        self.sd = SniperData(self, use_press=True)
        self.add_universe(self.select)
        self.spot_done = set()

    def select(self, fundamental):
        u = self.sd.u0(fundamental)
        if self.time.month in (3, 9) and self.time.day <= 7 and (self.time.year, self.time.month) not in self.spot_done:
            self.spot_done.add((self.time.year, self.time.month))
            want = {"LEH", "AAPL", "BSC", "WM", "BBBY", "MER"}
            for s in u:
                if s.value in want:
                    qs = self.sd.quarters(s, 2)
                    q0 = qs[0] if qs else {}
                    self.log(f"SPOT {self.time.date()} {s.value} cik={self.sd.cik(s)} "
                             f"eps={q0.get('eps')} rev={q0.get('revenue')} src={q0.get('source')} "
                             f"yoy_eps={self.sd.yoy(s, 'eps')} days_since_ann={self.sd.days_since_announcement(s)}")
        return []

    def on_end_of_algorithm(self):
        self.sd.report()
        self.log(f"RUNTIME seconds={time.time() - self.t0:.0f}")
