"""Merge SEC XBRL and press-release figures into one quarterly table,
dated by the earnings announcement (8-K item 2.02).

Output fundamentals/quarters.csv:
  cik, period_end, announce, available, eps, eps_prev, revenue, rev_prev, source
- source X  = XBRL quarter (first-reported value)
         XD = XBRL fourth quarter derived as year minus the three quarters
         P  = press release (parser v2), only when XBRL has no quarter for
              that announcement
- announce  = first 8-K item 2.02 filed 1-100 days after period_end
              (press rows: the release date itself; period_end left empty)
- available = day after announce; if no announcement is found, day after
              the XBRL filing date
- eps_prev / rev_prev = same quarter one year earlier (XBRL: the quarter
  ending 350-380 days before; press: the prior-year column of the release)
Usage: build_quarters.py  (run from the repository root)
"""

import bisect
import csv
import glob
from collections import defaultdict
from datetime import date, timedelta


def o(s):
    return date.fromisoformat(s[:10]).toordinal()


def ds(x):
    return date.fromordinal(x).isoformat()


def load_xbrl(group):
    q, y = defaultdict(dict), defaultdict(dict)
    for p in sorted(glob.glob(f"fundamentals/xbrl_{group}_*.csv")):
        for r in csv.DictReader(open(p)):
            s, e, f = o(r["start"]), o(r["end"]), o(r["filed"])
            n = e - s
            v = float(r["val"])
            tgt = q if 80 <= n <= 100 else y if 350 <= n <= 380 else None
            if tgt is not None and (e not in tgt[r["cik"]] or f < tgt[r["cik"]][e][1]):
                tgt[r["cik"]][e] = (v, f, s)
    return q, y


def derive_q4(q, y):
    """Q4 = year minus the three quarters inside it (all first-reported)."""
    out = defaultdict(dict)
    for cik, years in y.items():
        for e, (v, f, s) in years.items():
            if e in q[cik]:
                continue
            inside = [(qe, qv) for qe, qv in q[cik].items() if s < qe < e and qv[2] >= s - 5]
            if len(inside) == 3:
                out[cik][e] = (v - sum(x[1][0] for x in inside), f)
    return out


def main():
    ann = defaultdict(list)
    for r in csv.DictReader(open("earnings_dates/8k_202.csv")):
        ann[r["cik"]].append(o(r["filing_date"]))
    for v in ann.values():
        v.sort()

    def announce(cik, end):
        lst = ann.get(cik, [])
        i = bisect.bisect_right(lst, end)
        return lst[i] if i < len(lst) and lst[i] - end <= 100 else None

    eq, ey = load_xbrl("eps")
    rq, ry = load_xbrl("revenue")
    eq4, rq4 = derive_q4(eq, ey), derive_q4(rq, ry)

    rows = []
    used_ann = defaultdict(set)
    ciks = {c for c in set(eq) | set(rq) | set(eq4) | set(rq4) if c and c.isdigit()}
    for cik in ciks:
        ends = set(eq[cik]) | set(rq[cik]) | set(eq4[cik]) | set(rq4[cik])
        for e in sorted(ends):
            def pick(qd, q4d):
                if e in qd[cik]:
                    return qd[cik][e][0], qd[cik][e][1], "X"
                if e in q4d[cik]:
                    return q4d[cik][e][0], q4d[cik][e][1], "XD"
                return None, None, None
            ev, ef, es = pick(eq, eq4)
            rv, rf, rs = pick(rq, rq4)
            filed = min(x for x in (ef, rf) if x is not None)
            a = announce(cik, e)

            def prev(qd, q4d):
                for d in range(350, 381):
                    for src in (qd, q4d):
                        if e - d in src[cik]:
                            return src[cik][e - d][0]
                return None
            src = "XD" if "XD" in (es, rs) and "X" not in (es, rs) else "X"
            avail = (a + 1) if a else filed + 1
            if a:
                used_ann[cik].add(a)
            rows.append([cik, ds(e), ds(a) if a else "", ds(avail),
                         "" if ev is None else ev, "" if prev(eq, eq4) is None else prev(eq, eq4),
                         "" if rv is None else rv, "" if prev(rq, rq4) is None else prev(rq, rq4), src])
    n_x = len(rows)

    scale = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}
    n_p = 0
    for r in csv.DictReader(open("fundamentals/press_release_2004_2011.csv")):
        if not (r["eps"] or r["revenue"]) or not r["cik"].isdigit():
            continue
        a = o(r["date"])
        if a in used_ann[r["cik"]]:
            continue  # XBRL already covers this announcement
        k = scale.get(r["unit"])
        rev = float(r["revenue"]) * k if (r["revenue"] and k) else ""
        rprev = float(r["rev_prev"]) * k if (r["rev_prev"] and k) else ""
        rows.append([r["cik"], "", r["date"], ds(a + 1), r["eps"], r["eps_prev"], rev, rprev, "P"])
        n_p += 1
    rows.sort(key=lambda x: (int(x[0]), x[3]))
    with open("fundamentals/quarters.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cik", "period_end", "announce", "available", "eps", "eps_prev", "revenue", "rev_prev", "source"])
        w.writerows(rows)
    print(f"xbrl quarters={n_x} press quarters={n_p} total={len(rows)}")


if __name__ == "__main__":
    main()
