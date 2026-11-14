from AlgorithmImports import *
import bisect
import csv
import io
from datetime import date, timedelta

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/"
EXCH = {"NAS", "NYS", "NYSE", "ASE", "AMEX"}
DEAD = ["LEH", "BSC", "WM", "CFC", "WB", "MER", "ABK", "FNM", "FRE", "CC", "GM",
        "CIT", "NCC", "AIG", "MBI", "IMB", "NFI", "DLM", "SIRF", "BRCM"]
SAMPLE_YEARS = {2007, 2015, 2024}


def d(s):
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal()
    except Exception:
        return None


class SnipeRDataProbe6(QCAlgorithm):
    """Step 4: last prices of companies that died in 2008-2009.
    Step 5: classify U0 candidates as Morningstar common stock, other
    Morningstar type, no Morningstar but an operating company (CIK with an
    8-K item 2.02 release), or unidentified."""

    def initialize(self):
        self.set_start_date(2004, 9, 1)
        self.set_end_date(2026, 8, 10)
        self.set_cash(100000)
        self.tk = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "earnings_dates/cik_tickers.csv"))):
            t = (row["ticker"] or "").replace(".", "")
            o = d(row["filing_date"])
            if t and o:
                self.tk.setdefault(t, []).append((o, row["cik"]))
        for v in self.tk.values():
            v.sort()
        self.last_month = None
        self.yr = {}
        self.types = {}
        self.unid = {y: set() for y in SAMPLE_YEARS}
        self.dead_sym = {}
        self.add_universe(self.select)

    def cik_by_ticker(self, t, o):
        lst = self.tk.get(t.replace(".", ""))
        if not lst:
            return None
        i = bisect.bisect_left(lst, (o, ""))
        for j in (i - 1, i):
            if 0 <= j < len(lst) and abs(lst[j][0] - o) <= 400:
                return lst[j][1]
        return None

    def select(self, fundamental):
        key = (self.time.year, self.time.month)
        if key == self.last_month:
            return Universe.UNCHANGED
        self.last_month = key
        y = self.time.year
        o = self.time.date().toordinal()
        b = self.yr.setdefault(y, [0, 0, 0, 0, 0])
        for f in fundamental:
            t = f.symbol.value
            if key == (2008, 1) and t in DEAD and t not in self.dead_sym:
                self.dead_sym[t] = f.symbol
            if f.price < 5 or f.dollar_volume < 5e6:
                continue
            ex, st = None, None
            try:
                ex = f.security_reference.exchange_id
                st = f.security_reference.security_type
            except Exception:
                pass
            if ex and ex not in EXCH:
                continue
            b[0] += 1
            if ex:
                self.types[st] = self.types.get(st, 0) + 1
                if st == "ST00000001":
                    b[1] += 1
                else:
                    b[2] += 1
            elif self.cik_by_ticker(t, o):
                b[3] += 1
            else:
                b[4] += 1
                if y in SAMPLE_YEARS:
                    self.unid[y].add(t)
        return []

    def on_end_of_algorithm(self):
        self.log("DATA6 by_year (all, ms_common, ms_other_type, nofund_with_8k_cik, unidentified) " +
                 " ".join(f"{y}:{'/'.join(map(str, v))}" for y, v in sorted(self.yr.items())))
        self.log("DATA6 ms security types " + str(sorted(self.types.items(), key=lambda x: -x[1])[:10]))
        for y in sorted(self.unid):
            s = sorted(self.unid[y])
            self.log(f"DATA6 unidentified {y} n={len(s)} sample=" + " ".join(s[:80]))
        for t in DEAD:
            sym = self.dead_sym.get(t)
            if sym is None:
                self.log(f"DATA6 dead {t} not in universe 2008-01")
                continue
            try:
                h = self.history(sym, datetime(2008, 1, 1), datetime(2011, 1, 1), Resolution.DAILY, data_normalization_mode=DataNormalizationMode.RAW)
                if h is None or h.empty:
                    self.log(f"DATA6 dead {t} no history")
                    continue
                c = h["close"].droplevel(0) if h.index.nlevels > 1 else h["close"]
                last_t, last_c = c.index[-1], float(c.iloc[-1])
                prev = float(c.iloc[-21]) if len(c) > 21 else float("nan")
                self.log(f"DATA6 dead {t} last {last_t.date()} close {last_c:.4f} close_20d_before {prev:.4f} min {float(c.min()):.4f} rows {len(c)}")
            except Exception as e:
                self.log(f"DATA6 dead {t} error {type(e).__name__} {e}")
