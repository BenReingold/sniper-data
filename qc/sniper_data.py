"""SnipeR data module for QuantConnect (copy this file into a project and
`from sniper_data import SniperData`).

What it gives a backtest, point in time (only what was known that day):
- u0(fundamental): the U0 universe (U.S. common stocks on NYSE / Nasdaq /
  NYSE American, close >= 5 USD, 50-day average dollar volume >= 5M USD,
  252+ sessions seen, delisted included). Call it from the universe
  selection EVERY day; start the backtest at least one year before the
  first date you analyse (warm-up for the 252-session rule).
- cik(symbol): SEC company id. Morningstar CIK, else the ticker printed in
  8-K item 2.02 press releases (date-by-date within 400 days; else the one
  CIK that printed the ticker during the symbol's life). Rules: DECISIONS
  2026-11-12 and DECISIONS_ADDENDUM 2026-11-14.
- quarters(symbol, n): last n fiscal quarters known that day, newest first,
  from fundamentals/quarters.csv (XBRL, derived Q4, press releases), each
  available from the day after its earnings announcement.
- yoy(symbol, field): year-over-year growth of "eps" or "revenue" of the
  latest known quarter.
- days_since_announcement(symbol): calendar days since the last 8-K 2.02.
- sp500(fundamental): S&P 500 members that day as QuantConnect symbols, from
  the public daily list (index_membership/, fja05680, MIT licence), matched
  by ticker (dated old-ticker preferences first, BEFORE), then by later-ticker
  aliases (bankruptcy Q suffix, FNMA, FMCC), then by CIK, plus members the
  list loses to ticker collisions (COLLIDE). Checked against SPY constituents
  (from 2009-08) and SEC-filed SPDR holdings 2000, 2004, 2007
  (D10_CHECK_2026-11-18.md in the SnipeR project).
- report(): per-year coverage lines (call from on_end_of_algorithm).
Tables: https://github.com/BenReingold/sniper-data (SEC data only).
"""

from AlgorithmImports import *
import bisect
import csv
import io
from collections import deque
from datetime import date

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/"
EXCH = {"NAS", "NYS", "NYSE", "ASE", "AMEX"}
COMMON = "ST00000001"


def _o(s):
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal()
    except Exception:
        return None


def _f(s):
    try:
        v = float(s)
        return v if v == v else None
    except Exception:
        return None


class SniperData:
    def __init__(self, algo, use_press=True, min_price=5.0, min_dollar_volume=5e6,
                 min_sessions=252, dv_window=50, base=BASE):
        self.algo = algo
        self.use_press = use_press
        self.min_price = min_price
        self.min_dv = min_dollar_volume
        self.min_sessions = min_sessions
        self.dv_window = dv_window
        self.base = base
        self.st = {}            # symbol id -> state
        self.by_symbol = {}     # Symbol -> symbol id
        self.cov = {}           # year -> counters
        self.last_month = None
        self._load()

    # ------------------------------------------------------------------ load
    def _rows(self, path):
        return csv.DictReader(io.StringIO(self.algo.download(self.base + path)))

    def _load(self):
        self.ann = {}
        for r in self._rows("earnings_dates/8k_202.csv"):
            v = _o(r["filing_date"])
            if v:
                self.ann.setdefault(r["cik"], []).append(v)
        for v in self.ann.values():
            v.sort()

        self.tk, cnt = {}, {}
        for r in self._rows("earnings_dates/cik_tickers.csv"):
            t = (r["ticker"] or "").replace(".", "")
            v = _o(r["filing_date"])
            if t and v and len(t) > 1:
                self.tk.setdefault(t, []).append((v, r["cik"]))
                cnt[(r["cik"], t)] = cnt.get((r["cik"], t), 0) + 1
        for t in list(self.tk):
            # a press-release ticker counts only if the CIK printed it twice
            lst = sorted(x for x in self.tk[t] if cnt.get((x[1], t), 0) >= 2)
            if lst:
                self.tk[t] = lst
            else:
                del self.tk[t]

        self.q = {}
        for r in self._rows("fundamentals/quarters.csv"):
            if r["source"] == "P" and not self.use_press:
                continue
            av = _o(r["available"])
            if av is None:
                continue
            self.q.setdefault(r["cik"], []).append((
                av, _o(r["announce"]) if r["announce"] else None,
                _o(r["period_end"]) if r["period_end"] else None,
                _f(r["eps"]), _f(r["eps_prev"]), _f(r["revenue"]), _f(r["rev_prev"]), r["source"]))
        for v in self.q.values():
            v.sort(key=lambda x: x[0])
        self.qa = {c: [x[0] for x in v] for c, v in self.q.items()}
        self.algo.log(f"SniperData loaded: announcements={sum(map(len, self.ann.values()))} "
                      f"tickers={len(self.tk)} quarter_ciks={len(self.q)} press={self.use_press}")

    # -------------------------------------------------------------- identity
    def _today(self):
        return self.algo.time.date().toordinal()

    def _ticker_cik(self, t, today, first):
        lst = self.tk.get(t.replace(".", ""))
        if not lst:
            return None, None
        i = bisect.bisect_left(lst, (today, ""))
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(lst):
                gap = abs(lst[j][0] - today)
                if gap <= 400 and (best is None or gap < best[0]):
                    best = (gap, lst[j][1])
        if best:
            return best[1], "TICKER"
        life = {c for v, c in lst if v >= first - 400}
        if len(life) == 1:
            return life.pop(), "LIFE"
        return None, None

    def _state(self, f, today):
        sid = str(f.symbol.id)
        s = self.st.get(sid)
        if s is None:
            s = {"first": today, "n": 0, "dv": deque(maxlen=self.dv_window), "dvsum": 0.0,
                 "cik": None, "how": None, "checked": None, "sym": f.symbol}
            self.st[sid] = s
            self.by_symbol[f.symbol] = sid
        return s

    def _identify(self, f, s, today):
        if s["checked"] is not None and today - s["checked"] < 30 and s["how"] != "MS":
            return
        c = None
        try:
            c0 = f.company_reference.cik
            c = str(int(c0)) if c0 else None
        except Exception:
            c = None
        if c:
            s["cik"], s["how"] = c, "MS"
        else:
            s["cik"], s["how"] = self._ticker_cik(f.symbol.value, today, s["first"])
        s["checked"] = today

    def cik(self, symbol):
        sid = self.by_symbol.get(symbol)
        return self.st[sid]["cik"] if sid else None

    # -------------------------------------------------------------- universe
    def u0(self, fundamental):
        today = self._today()
        y = self.algo.time.year
        month = (y, self.algo.time.month)
        sample = month != self.last_month
        self.last_month = month
        c = self.cov.setdefault(y, {}) if sample else None
        out = []
        for f in fundamental:
            s = self._state(f, today)
            dv = f.dollar_volume or 0.0
            if len(s["dv"]) == s["dv"].maxlen:
                s["dvsum"] -= s["dv"][0]
            s["dv"].append(dv)
            s["dvsum"] += dv
            s["n"] += 1
            if f.price < self.min_price or len(s["dv"]) < self.dv_window or \
                    s["dvsum"] / len(s["dv"]) < self.min_dv:
                continue
            ex = st = None
            try:
                ex = f.security_reference.exchange_id
                st = f.security_reference.security_type
            except Exception:
                pass
            if ex and ex not in EXCH:
                continue
            self._identify(f, s, today)
            reason = None
            if ex and st != COMMON:
                reason = "not_common"
            elif not ex and not s["cik"]:
                reason = "unidentified"
            elif s["n"] < self.min_sessions:
                reason = "short_history"
            if sample:
                c["candidates"] = c.get("candidates", 0) + 1
                if reason:
                    c[reason] = c.get(reason, 0) + 1
            if reason:
                continue
            out.append(f.symbol)
            if sample:
                self._count(c, s, today, bool(ex))
        return out

    def _count(self, c, s, today, has_ms):
        def add(k):
            c[k] = c.get(k, 0) + 1
        add("u0")
        add("ms" if has_ms else "no_ms")
        if s["how"]:
            add("cik_" + s["how"])
        else:
            add("no_cik")
        lq = self._latest(s["cik"], today) if s["cik"] else None
        if lq and today - lq[0] <= 200:
            add("q_" + lq[7])
        else:
            add("q_none")
        la = self._last_ann(s["cik"], today) if s["cik"] else None
        add("ann_120d" if la and today - la <= 120 else "ann_none")

    # ---------------------------------------------------------- fundamentals
    def _latest(self, cik, today):
        lst = self.q.get(cik)
        if not lst:
            return None
        i = bisect.bisect_right(self.qa[cik], today) - 1
        return lst[i] if i >= 0 else None

    def quarters(self, symbol, n=8):
        """Last n quarters known today, newest first: dicts with available,
        announce, period_end (ordinals or None), eps, revenue, source."""
        c = self.cik(symbol)
        lst = self.q.get(c) if c else None
        if not lst:
            return []
        today = self._today()
        i = bisect.bisect_right(self.qa[c], today)
        out, seen = [], set()
        for x in reversed(lst[:i]):
            key = x[2] or x[1]
            if key in seen:
                continue
            seen.add(key)
            out.append({"available": x[0], "announce": x[1], "period_end": x[2], "eps": x[3],
                        "eps_prev": x[4], "revenue": x[5], "rev_prev": x[6], "source": x[7]})
            if len(out) >= n:
                break
        return out

    def yoy(self, symbol, field="eps"):
        """Growth of the latest known quarter against the same quarter a year
        earlier. XBRL rows carry the prior-year value; for press rows the
        quarter announced 330-400 days earlier is used."""
        qs = self.quarters(symbol, 6)
        if not qs:
            return None
        cur = qs[0]
        now = cur[field]
        prev = cur[field + "_prev" if field == "eps" else "rev_prev"] if cur["source"] != "P" else None
        if prev is None and cur["announce"]:
            for x in qs[1:]:
                if x["announce"] and 330 <= cur["announce"] - x["announce"] <= 400:
                    prev = x[field]
                    break
        if now is None or prev is None or prev == 0:
            return None
        return now / abs(prev) - 1 if prev > 0 else (now - prev) / abs(prev)

    # --------------------------------------------------------- announcements
    def _last_ann(self, cik, today):
        lst = self.ann.get(cik)
        if not lst:
            return None
        i = bisect.bisect_left(lst, today) - 1   # filed before today: known today
        return lst[i] if i >= 0 else None

    def days_since_announcement(self, symbol):
        c = self.cik(symbol)
        la = self._last_ann(c, self._today()) if c else None
        return self._today() - la if la else None

    # ---------------------------------------------------------------- S&P 500
    # Later ticker in the public list -> tickers the company used at the time
    # (tried in order; a candidate is used only if it trades that day and is
    # not already taken by another member). Built 2026-11-18 from the list of
    # unmatched members 1998-2010; from Claude's knowledge, checked by the
    # match test, see index_membership/README.md.
    ALIAS = {
        "FNMA": ["FNM"], "FMCC": ["FRE"], "AABA": ["YHOO"], "AAMRQ": ["AMR"], "ABI": ["PKN", "PEB"],
        "ACKH": ["ACK"], "ARNC": ["AA"], "AZAA": ["AZA"], "BBT": ["BBK"], "BHGE": ["BHI"],
        "BHMSQ": ["BS"], "BMGCA": ["BMG"], "CBS": ["VIAB", "VIA"], "CCTYQ": ["CC"], "CEG": ["BGE"],
        "CFC": ["CCR"], "CNP": ["HOU", "REI"], "DALRQ": ["DAL"], "DCNAQ": ["DCN"], "DXC": ["CSC"],
        "EKDKQ": ["EK"], "ENRNQ": ["ENE"], "ETS": ["CS"], "EXC": ["UCM"], "FBF": ["FLT"],
        "FLTWQ": ["FLE"], "FTLA": ["FTL"], "FWLT": ["FW"], "GAPTQ": ["GAP"], "HCA": ["COL"],
        "HSH": ["SLE"], "INCLF": ["N"], "L": ["LTR"], "LDWB": ["LDW"], "MEE": ["FLR"],
        "MS": ["MWD"], "MSI": ["MOT"], "MTLQQ": ["GM"], "NEE": ["FPL"], "NRTLQ": ["NT"],
        "OMX": ["BCC"], "OWENQ": ["OWC"], "PGN": ["CPL"], "PHA": ["PNU"], "RDSA": ["RD"],
        "RSHCQ": ["RSH", "TAN"], "RYI": ["RT"], "S": ["FON"], "SAF": ["SAFC"], "SGID": ["SGI"],
        "TGT": ["DH"], "TMCA": ["TMC"], "TWX": ["AOL"], "UAWGQ": ["U"], "WAMUQ": ["WM"],
        "WCOEQ": ["WCOM"], "ANDV": ["TSO"], "BTUUQ": ["BTU", "BTUW"], "CITGQ": ["CIT"], "ABKFQ": ["ABK"],
        "CPNLQ": ["CPN"], "DPHIQ": ["DPH"], "FTR": ["CZN"], "LDOS": ["SAI"], "ATGE": ["DV"],
        "LEHMQ": ["LEH"], "VSTNQ": ["VC"], "WNDXQ": ["WIN"], "TT": ["ASD"], "TPR": ["COH"],
        "IAC": ["IACI"], "WYND": ["WYN"], "SUNEQ": ["WFR"], "ES": ["NU"], "LB": ["LTD"],
        "ANRZQ": ["ANR"], "AFSA": ["AFS"], "CITA": ["CIT"], "EP": ["EPG"], "GX": ["GBLX"],
        "WYE": ["AHP"], "SXCL": ["ADPT"], "AGN": ["ACT"],
    }
    # Tickers that the public list gives to a company which, before the date,
    # traded under another ticker while a different company may have held
    # this one. Before the date the old tickers are tried first (if one trades
    # that day and is not taken); otherwise the list ticker is used directly.
    # Dates are Claude's [S] (a later date is safe: once the old ticker stops
    # trading the direct match is used). Added 2026-11-18 after the check of
    # D10_CHECK_2026-11-18.md: the direct match had picked other companies
    # (Liberty Media for L, PAR Technology for PTC, Jefferies for JEF, ...).
    BEFORE = {
        "WM": (date(2008, 11, 1).toordinal(), ["WMI"]),
        "L": (date(2009, 1, 1).toordinal(), ["LTR"]),
        "LB": (date(2013, 4, 1).toordinal(), ["LTD"]),
        "MS": (date(2008, 1, 1).toordinal(), ["MWD"]),
        "MSI": (date(2011, 1, 5).toordinal(), ["MOT"]),
        "PTC": (date(2013, 2, 1).toordinal(), ["PMTC"]),
        "SAF": (date(2008, 9, 23).toordinal(), ["SAFC"]),
        "TT": (date(2007, 8, 1).toordinal(), ["ASD"]),
        "ABI": (date(2001, 1, 1).toordinal(), ["PEB", "PKN"]),
        "COP": (date(2002, 9, 1).toordinal(), ["P"]),
        "CMI": (date(2001, 6, 1).toordinal(), ["CUM"]),
        "CAR": (date(2006, 9, 1).toordinal(), ["CD"]),
        "JEF": (date(2018, 5, 24).toordinal(), ["LUK"]),
        "OMX": (date(2004, 11, 1).toordinal(), ["BCC"]),
        "ES": (date(2015, 5, 1).toordinal(), ["NU"]),
    }
    # S&P 500 members missing from the public list because two members of
    # the time later share one ticker (duplicate removed in the list): added
    # by their ticker at the time while it trades, inside [start, end).
    # Found by the SPDR (SPY) holdings check of 2000, 2004, 2007
    # (D10_CHECK_2026-11-18.md). End dates: merger or removal dates
    # (Claude's knowledge [S]; ACE from S&P announcements). Start dates are
    # 1996 for long-time members; where the entry date is not known the
    # first SPDR date that confirms membership is used [S], so the years
    # before it stay missing rather than wrong.
    COLLIDE = [
        (["FON"], date(1996, 1, 2), date(2005, 8, 12)),     # Sprint (list: S = Sears)
        (["SBC"], date(1996, 1, 2), date(2005, 11, 18)),    # SBC (list: T = AT&T Corp)
        (["TYC"], date(1996, 1, 2), date(2016, 9, 3)),      # Tyco (list: JCI); merger closed 2016-09-02
        (["WPI", "ACT"], date(2000, 9, 29), date(2015, 3, 17)),  # Watson/Actavis (list: AGN)
        (["ACE"], date(2004, 9, 30), date(2008, 7, 18)),    # ACE (list: CB); removed 2008-07-17
        (["ACE"], date(2010, 7, 15), date(2016, 1, 14)),    # ACE re-added after close 2010-07-14
        (["AOL"], date(2000, 9, 29), date(2001, 1, 12)),    # AOL (list: TWX)
        (["CMB"], date(1996, 1, 2), date(2001, 1, 1)),      # Chase Manhattan (list: JPM)
        (["FTU"], date(1996, 1, 2), date(2001, 9, 4)),      # First Union (list: WB)
        (["FSR"], date(1999, 1, 4), date(2001, 2, 28)),     # Firstar (list: USB)
        (["PE"], date(1996, 1, 2), date(2000, 10, 20)),     # PECO (list: EXC, via UCM)
    ]

    def _load_sp500(self):
        self.sp_dates, self.sp_lists = [], []
        for r in self._rows("index_membership/sp500_daily_fja05680.csv"):
            self.sp_dates.append(_o(r["date"]))
            self.sp_lists.append(r["tickers"].split(","))
        self.sp_cik = {}
        for r in self._rows("index_membership/sp500_cik_intervals.csv"):
            self.sp_cik.setdefault(self._norm(r["ticker"]), []).append(
                (_o(r["start"]), _o(r["end"]) if r["end"] else 10 ** 7, r["cik"]))

    @staticmethod
    def _norm(t):
        return t.replace(".", "").replace("-", "").replace(" ", "").upper()

    def sp500(self, fundamental):
        """Set of Symbols in the S&P 500 today (public list, see module notes)."""
        if not hasattr(self, "sp_dates"):
            self._load_sp500()
        today = self._today()
        i = bisect.bisect_right(self.sp_dates, today) - 1
        if i < 0:
            return set()
        by_t, by_c = {}, {}
        for f in fundamental:
            by_t.setdefault(self._norm(f.symbol.value), f.symbol)
            try:
                c0 = f.company_reference.cik
                if c0:
                    by_c[str(int(c0))] = f.symbol
            except Exception:
                pass
        for sid, st in self.st.items():
            if st["cik"] and st["cik"] not in by_c:
                by_c[st["cik"]] = st["sym"]
        out, self.sp_missing, self.sp_alias_used = set(), [], []
        later = []
        listed = {self._norm(t) for t in self.sp_lists[i]}
        for t in self.sp_lists[i]:
            n = self._norm(t)
            s = None
            pre = self.BEFORE.get(n)
            if pre and today < pre[0]:
                for a in pre[1]:
                    cand = by_t.get(a)
                    if cand is not None and cand not in out and a not in listed:
                        s = cand
                        self.sp_alias_used.append(f"{t}>{a}")
                        break
            if s is None:
                s = by_t.get(n)
                if s is not None and s in out:
                    s = None
            if s is None:
                later.append((t, n))
            else:
                out.add(s)
        for t, n in later:
            s = None
            for a in self.ALIAS.get(n, []):
                cand = by_t.get(a)
                if cand is not None and cand not in out:
                    s = cand
                    self.sp_alias_used.append(f"{t}>{a}")
                    break
            if s is None:
                for a, b, c in self.sp_cik.get(n, []):
                    if a - 5 <= today <= b + 5 and c in by_c:
                        s = by_c[c]
                        break
            if s is None:
                self.sp_missing.append(t)
            else:
                out.add(s)
        d = date.fromordinal(today)
        for tickers, a, b in self.COLLIDE:
            if a <= d < b:
                for x in tickers:
                    cand = by_t.get(x)
                    if cand is not None and cand not in out:
                        out.add(cand)
                        self.sp_alias_used.append(f"+{x}")
                        break
        return out

    # ----------------------------------------------------------------- report
    def report(self):
        keys = ["candidates", "u0", "not_common", "unidentified", "short_history", "ms", "no_ms",
                "cik_MS", "cik_TICKER", "cik_LIFE", "no_cik", "q_X", "q_XD", "q_P", "q_none",
                "ann_120d", "ann_none"]
        self.algo.log("SniperData coverage (first trading day of each month, summed per year): " + ",".join(keys))
        for y in sorted(self.cov):
            c = self.cov[y]
            self.algo.log(f"SniperData {y}: " + ",".join(str(c.get(k, 0)) for k in keys))
