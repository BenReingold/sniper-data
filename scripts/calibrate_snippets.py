"""Compare parsed press-release EPS / revenue with SEC XBRL first-reported
quarterly values. A release is matched to the XBRL quarter of the same CIK
that ends 5-75 days before the release date.
Usage: calibrate_snippets.py PARSED.csv FUNDAMENTALS_DIR
"""

import bisect
import csv
import glob
import sys
from collections import Counter, defaultdict
from datetime import date

SCALE = {"thousands": 1e3, "millions": 1e6, "billions": 1e9, "": 1.0}


def o(s):
    return date.fromisoformat(s[:10]).toordinal()


def load(group, fdir):
    m = defaultdict(list)
    for p in sorted(glob.glob(f"{fdir}/xbrl_{group}_*.csv")):
        for r in csv.DictReader(open(p)):
            s, e = o(r["start"]), o(r["end"])
            if 80 <= e - s <= 100:
                m[r["cik"]].append((e, float(r["val"]), r["concept"], o(r["filed"])))
    for v in m.values():
        v.sort()
    return m


def quarter(m, cik, d):
    lst = m.get(cik)
    if not lst:
        return None
    i = bisect.bisect_right(lst, (d - 5, 1e30, "", 0)) - 1
    # the XBRL value must be the first report of that quarter: filed 0-75 days after the release
    if i >= 0 and d - lst[i][0] <= 75 and 0 <= lst[i][3] - d <= 75:
        return lst[i]
    return None


def confirmations(rows):
    """A value is confirmed when the release about 1 year later prints it as
    its prior-year figure (same CIK, 330-400 days later)."""
    by = defaultdict(list)
    for r in rows:
        by[r["cik"]].append(r)
    conf_e, conf_r = set(), set()
    for lst in by.values():
        lst.sort(key=lambda r: r["date"])
        ds = [o(r["date"]) for r in lst]
        for i, r in enumerate(lst):
            j = bisect.bisect_left(ds, ds[i] + 330)
            while j < len(lst) and ds[j] <= ds[i] + 400:
                n = lst[j]
                if r["eps"] and n["eps_prev"] and abs(float(r["eps"]) - float(n["eps_prev"])) <= 0.005:
                    conf_e.add(r["acc"])
                if r["revenue"] and n["rev_prev"] and float(r["revenue"]) and abs(float(r["revenue"]) - float(n["rev_prev"])) <= 0.002 * abs(float(r["revenue"])):
                    conf_r.add(r["acc"])
                j += 1
    return conf_e, conf_r


def main():
    parsed, fdir = sys.argv[1], sys.argv[2]
    rows = list(csv.DictReader(open(parsed)))
    conf_e, conf_r = confirmations(rows)
    print(f"confirmed by next-year release: eps {len(conf_e)} of {sum(1 for r in rows if r['eps'])}, revenue {len(conf_r)} of {sum(1 for r in rows if r['revenue'])}")
    eps_x, rev_x = load("eps", fdir), load("revenue", fdir)
    st = Counter()
    by_year = defaultdict(Counter)
    bad_eps, bad_rev = [], []
    for r in rows:
        y = r["date"][:4]
        d = o(r["date"])
        q = quarter(eps_x, r["cik"], d)
        if q:
            st["eps_ref"] += 1
            by_year[y]["eps_ref"] += 1
            if r["eps"]:
                st["eps_found"] += 1
                v = float(r["eps"])
                ok = abs(v - q[1]) <= max(0.011, 0.01 * abs(q[1]))
                st["eps_ok"] += ok
                if r["acc"] in conf_e:
                    st["eps_conf"] += 1
                    st["eps_conf_ok"] += ok
                by_year[y]["eps_ok"] += ok
                if not ok and len(bad_eps) < 15:
                    bad_eps.append((r["cik"], r["date"], v, q[1], r["eps_label"]))
        q = quarter(rev_x, r["cik"], d)
        if q:
            st["rev_ref"] += 1
            if r["revenue"]:
                st["rev_found"] += 1
                v = float(r["revenue"]) * SCALE.get(r["unit"], 1.0)
                ok = abs(v - q[1]) <= 0.01 * abs(q[1])
                st["rev_ok"] += ok
                if r["acc"] in conf_r:
                    st["rev_conf"] += 1
                    st["rev_conf_ok"] += ok
                if not ok:
                    for alt in (1.0, 1e3, 1e6):
                        if abs(float(r["revenue"]) * alt - q[1]) <= 0.01 * abs(q[1]):
                            st["rev_ok_other_scale"] += 1
                            break
                    if len(bad_rev) < 15:
                        bad_rev.append((r["cik"], r["date"], r["revenue"], r["unit"], q[1], r["rev_label"]))
    print(dict(st))
    if st["eps_found"]:
        print(f"EPS: found {st['eps_found']}/{st['eps_ref']} = {st['eps_found']/st['eps_ref']:.1%}, "
              f"correct {st['eps_ok']}/{st['eps_found']} = {st['eps_ok']/st['eps_found']:.1%}")
    if st["rev_found"]:
        print(f"Revenue: found {st['rev_found']}/{st['rev_ref']} = {st['rev_found']/st['rev_ref']:.1%}, "
              f"correct {st['rev_ok']}/{st['rev_found']} = {st['rev_ok']/st['rev_found']:.1%}")
    if st["eps_conf"]:
        print(f"EPS confirmed subset: correct {st['eps_conf_ok']}/{st['eps_conf']} = {st['eps_conf_ok']/st['eps_conf']:.1%}")
    if st["rev_conf"]:
        print(f"Revenue confirmed subset: correct {st['rev_conf_ok']}/{st['rev_conf']} = {st['rev_conf_ok']/st['rev_conf']:.1%}")
    print("by year eps ref/ok:", {y: (c["eps_ref"], c["eps_ok"]) for y, c in sorted(by_year.items())})
    print("EPS misses:", *bad_eps, sep="\n  ")
    print("Revenue misses:", *bad_rev, sep="\n  ")


if __name__ == "__main__":
    main()
