from AlgorithmImports import *

TICKERS = ["LEH", "BSC", "MER", "WM", "CFC", "WB", "TWX", "ABK", "ACS", "AA",
           "FNM", "FRE", "NCC", "CIT", "GM", "CC", "AAPL", "JPM", "XOM", "MSFT"]


class SnipeRGapCheck(QCAlgorithm):
    """Do dead companies have Morningstar fundamentals in QuantConnect?
    Checked two ways on 2007-06: the security's own Fundamentals object and
    the Fundamental universe record for the same symbol."""

    def initialize(self):
        self.set_start_date(2007, 6, 4)
        self.set_end_date(2007, 6, 8)
        self.set_cash(100000)
        self.syms = {}
        for t in TICKERS:
            try:
                self.syms[t] = self.add_equity(t, Resolution.DAILY).symbol
            except Exception as e:
                self.log(f"GAP add {t} failed {e}")
        self.uni_seen = {}
        self.add_universe(self.select)
        self.done = False

    def select(self, fundamental):
        want = {str(s.id): t for t, s in self.syms.items()}
        for f in fundamental:
            t = want.get(str(f.symbol.id))
            if t and t not in self.uni_seen:
                self.uni_seen[t] = self.describe(f)
        return []

    def describe(self, f):
        out = {"has": None, "name": None, "cik": None, "ex": None, "rev": None, "eps": None, "file": None}
        try: out["has"] = f.has_fundamental_data
        except Exception: pass
        try: out["name"] = f.company_reference.legal_name
        except Exception: pass
        try: out["cik"] = f.company_reference.cik
        except Exception: pass
        try: out["ex"] = f.security_reference.exchange_id
        except Exception: pass
        try: out["rev"] = f.financial_statements.income_statement.total_revenue.three_months
        except Exception: pass
        try: out["eps"] = f.earning_reports.basic_eps.three_months
        except Exception: pass
        try: out["file"] = str(f.financial_statements.file_date.value)[:10]
        except Exception: pass
        return out

    def on_data(self, data):
        if self.done:
            return
        self.done = True
        for t, s in self.syms.items():
            own = self.describe(self.securities[s].fundamentals) if self.securities[s].fundamentals else "none"
            price = self.securities[s].price
            self.log(f"GAP {t} id={s.id} price={price} own={own}")

    def on_end_of_algorithm(self):
        for t in TICKERS:
            self.log(f"GAP-UNI {t} {self.uni_seen.get(t, 'not in universe file')}")
