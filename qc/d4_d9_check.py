from AlgorithmImports import *
from datetime import datetime

ETFS = ["SPY", "TLT", "AGG", "GLD", "IWM", "TQQQ", "XLU"]
IPOS = {"GOOG": "2004-08-19", "META": "2012-05-18", "TSLA": "2010-06-29", "V": "2008-03-19",
        "BX": "2007-06-22", "MA": "2006-05-25", "UBER": "2019-05-10", "SNOW": "2020-09-16"}


class SnipeRD4D9Check(QCAlgorithm):
    """D4: is QuantConnect's ADJUSTED ETF series a total return with dividends
    reinvested? Compared with own reinvestment of raw closes and dividends,
    2011-01-03 to 2025-12-31. D9: IPO date fields against known IPO dates.
    Examines no strategy returns; not a trial."""

    def initialize(self):
        self.set_start_date(2026, 8, 3)
        self.set_end_date(2026, 8, 7)
        self.set_cash(100000)
        self.syms = {t: self.add_equity(t, Resolution.DAILY).symbol for t in ETFS + list(IPOS)}
        self.done = False

    def on_data(self, data):
        if self.done:
            return
        self.done = True
        a, b = datetime(2011, 1, 3), datetime(2025, 12, 31)
        for t in ETFS:
            s = self.syms[t]
            try:
                raw = self.history(s, a, b, Resolution.DAILY, data_normalization_mode=DataNormalizationMode.RAW)["close"]
                adj = self.history(s, a, b, Resolution.DAILY, data_normalization_mode=DataNormalizationMode.ADJUSTED)["close"]
                raw = raw.droplevel(0) if raw.index.nlevels > 1 else raw
                adj = adj.droplevel(0) if adj.index.nlevels > 1 else adj
                divs = self.history(Dividend, s, a, b)
                dmap = {}
                if divs is not None and not divs.empty:
                    col = "distribution" if "distribution" in divs.columns else divs.columns[0]
                    dd = divs[col].droplevel(0) if divs.index.nlevels > 1 else divs[col]
                    for ts, v in dd.items():
                        dmap[ts.date()] = dmap.get(ts.date(), 0.0) + float(v)
                tr, prev = 1.0, None
                splits = 0
                for ts, c in raw.items():
                    c = float(c)
                    if prev is not None:
                        r = (c + dmap.get(ts.date(), 0.0)) / prev
                        if r < 0.6 or r > 1.6:
                            splits += 1   # split day: skip (raw price jumps)
                        else:
                            tr *= r
                    prev = c
                adj_tr = float(adj.iloc[-1]) / float(adj.iloc[0])
                px = float(raw.iloc[-1]) / float(raw.iloc[0])
                self.log(f"D4 {t} own_reinvest={tr:.4f} adjusted={adj_tr:.4f} price_only={px:.4f} dividends={len(dmap)} split_days_skipped={splits}")
            except Exception as e:
                self.log(f"D4 {t} error {type(e).__name__} {e}")
        for t, ipo in IPOS.items():
            s = self.syms[t]
            f = self.securities[s].fundamentals
            ms = None
            try:
                ms = f.security_reference.ipo_date
            except Exception:
                pass
            self.log(f"D9 {t} known_ipo={ipo} morningstar_ipo={str(ms)[:10]} symbol_first_date={str(s.id.date)[:10]} market_cap={getattr(f, 'market_cap', None)}")
