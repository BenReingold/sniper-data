from AlgorithmImports import *
import bisect
import csv
import io
import re
from datetime import date, timedelta

BASE = "https://raw.githubusercontent.com/BenReingold/sniper-data/main/earnings_dates/"
AUDIT = {"LEH", "BSC", "MER", "WM", "WAMU", "CFC", "WB", "YHOO", "DELL", "MON",
         "CELG", "EMC", "RAI", "ESRX", "BRCM", "TWX", "AA", "AAPL", "NKE", "GE"}
EXCH = {"NAS", "NYS", "NYSE", "ASE", "AMEX"}
DROP = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD",
        "LIMITED", "PLC", "LLC", "LP", "L", "P", "THE", "NV", "SA", "AG", "HOLDING",
        "HOLDINGS", "GROUP", "TRUST", "DEL", "DE"}


def norm(s):
    s = (s or "").upper()
    s = re.sub(r"/[A-Z]{2,3}/?", " ", s)          # SEC state tags like /DE/
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in DROP]
    return " ".join(words)


def d(s):
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).toordinal()
    except Exception:
        return None


class SnipeRMapProbe(QCAlgorithm):
    """CIK-to-symbol mapping probe: Morningstar CIK, then validated name match."""

    def initialize(self):
        self.set_start_date(2004, 9, 1)
        self.set_end_date(2026, 10, 30)
        self.set_cash(100000)
        self.last_month = None
        self.sec = {}   # symbol id -> dict
        self.add_universe(self.select)

    def select(self, fundamental):
        key = (self.time.year, self.time.month)
        if key == self.last_month:
            return Universe.UNCHANGED
        self.last_month = key
        y = self.time.year
        for f in fundamental:
            try:
                if f.price < 5 or f.dollar_volume < 5e6:
                    continue
                ex = f.security_reference.exchange_id
                if ex not in EXCH:
                    continue
            except Exception:
                continue
            sid = str(f.symbol.id)
            r = self.sec.get(sid)
            if r is None:
                r = {"t": set(), "cik": set(), "names": set(), "fd": set(), "years": set()}
                self.sec[sid] = r
            r["t"].add(f.symbol.value)
            r["years"].add(y)
            cr = f.company_reference
            for nm in (cr.legal_name, cr.standard_name, cr.short_name):
                if nm:
                    r["names"].add(nm)
            if cr.cik:
                r["cik"].add(str(int(cr.cik)) if str(cr.cik).isdigit() else str(cr.cik))
            try:
                fd = f.financial_statements.file_date.value
                if fd and fd.year > 1990:
                    r["fd"].add(date(fd.year, fd.month, fd.day).toordinal())
            except Exception:
                pass
        return []

    def on_end_of_algorithm(self):
        ents = list(csv.DictReader(io.StringIO(self.download(BASE + "entities.csv"))))
        dates = {}
        for row in csv.DictReader(io.StringIO(self.download(BASE + "8k_202.csv"))):
            o = d(row["filing_date"])
            if o:
                dates.setdefault(row["cik"], []).append(o)
        for v in dates.values():
            v.sort()
        idx = {}
        for e in ents:
            names = [e["name"]] + [x.split("~")[0] for x in (e.get("former_names") or "").split("|") if x]
            for nm in names:
                k = norm(nm)
                if k:
                    idx.setdefault(k, set()).add(e["cik"])
        self.log(f"MAP sec entities={len(ents)} ciks_with_dates={len(dates)} name_keys={len(idx)} symbols={len(self.sec)}")

        def score(cik, fds):
            ds = dates.get(cik)
            if not ds or not fds:
                return None
            hit = 0
            for fd in fds:
                i = bisect.bisect_right(ds, fd)
                if i > 0 and fd - ds[i - 1] <= 75:
                    hit += 1
            return hit / len(fds)

        stats = {"ms": 0, "ms_valid": 0, "ms_nodates": 0, "name_valid": 0, "name_only": 0,
                 "name_ambig": 0, "none": 0, "no_names": 0}
        ms_scores = []
        by_year = {}
        audit_lines = []
        for sid, r in self.sec.items():
            fds = sorted(r["fd"])
            how, cik = "none", None
            ms = [c for c in r["cik"] if c]
            if ms:
                stats["ms"] += 1
                c = ms[0]
                s = score(c, fds)
                if s is not None:
                    ms_scores.append(s)
                if c in dates:
                    how, cik = "ms", c
                    if s is not None and s >= 0.5:
                        stats["ms_valid"] += 1
                else:
                    stats["ms_nodates"] += 1
            if how == "none":
                cands = set()
                for nm in r["names"]:
                    cands |= idx.get(norm(nm), set())
                cands = {c for c in cands if c in dates}
                if not r["names"]:
                    stats["no_names"] += 1
                if cands:
                    scored = [(score(c, fds), c) for c in cands]
                    good = [(s, c) for s, c in scored if s is not None and s >= 0.5]
                    if len(good) >= 1:
                        good.sort(reverse=True)
                        how, cik = "name_valid", good[0][1]
                        stats["name_valid"] += 1
                    elif len(cands) == 1 and not fds:
                        how, cik = "name_only", next(iter(cands))
                        stats["name_only"] += 1
                    else:
                        stats["name_ambig"] += 1
                else:
                    stats["none"] += 1
            for y in r["years"]:
                b = by_year.setdefault(y, [0, 0, 0])
                b[0] += 1
                if how in ("ms", "name_valid"):
                    b[1] += 1
                if how == "name_only":
                    b[2] += 1
            if r["t"] & AUDIT:
                audit_lines.append(f"{sorted(r['t'])[:3]} names={sorted(r['names'])[:2]} ms_cik={sorted(r['cik'])} fds={len(fds)} -> {how} {cik}")

        ms_scores.sort()
        n = len(ms_scores)
        q = lambda p: round(ms_scores[int(p * (n - 1))], 2) if n else None
        self.log(f"MAP stats {stats}")
        self.log(f"MAP ms_cik score n={n} p10={q(0.1)} p25={q(0.25)} p50={q(0.5)} share>=0.5={sum(1 for s in ms_scores if s >= 0.5)/max(n,1):.3f}")
        self.log("MAP by_year (symbols, mapped validated, name_only) " + " ".join(f"{y}:{v[0]}/{v[1]}/{v[2]}" for y, v in sorted(by_year.items())))
        for line in sorted(audit_lines)[:40]:
            self.log("MAP audit " + line)
