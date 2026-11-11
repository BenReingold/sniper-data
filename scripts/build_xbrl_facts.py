"""Extract quarterly and annual income facts from SEC companyfacts.zip.

Source: SEC bulk file companyfacts.zip (XBRL facts of all filers, from 2009).
For each CIK and each concept below, the FIRST filed value of each period is kept
(point in time: what was known then), with its filing date and form; later
restatements are dropped.

Only quarter-length (80-100 days) and year-length (350-380 days) periods are
kept. Per (cik, period) one value: the highest-priority concept of its group
(order in GROUPS; code = index, see xbrl_concepts.txt), first filing.

Outputs (CSV split into parts below 90 MB, plain text for QuantConnect):
  fundamentals/xbrl_eps_N.csv      cik,concept,start,end,val,filed,form
  fundamentals/xbrl_revenue_N.csv  same columns
  fundamentals/xbrl_netincome_N.csv
"""

import csv
import json
from datetime import date
import os
import sys
import zipfile

ZIP_PATH, OUT_DIR = sys.argv[1], sys.argv[2]

GROUPS = {
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic",
            "EarningsPerShareBasicAndDiluted"],
    "revenue": ["Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
                "RevenuesNetOfInterestExpense", "InterestAndDividendIncomeOperating"],
    "netincome": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
}
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "8-K", "10-KT", "10-QT"}
MAX_BYTES = 90_000_000


def days(s, e):
    try:
        return (date.fromisoformat(e) - date.fromisoformat(s)).days
    except Exception:
        return -1


def keep_period(s, e):
    n = days(s, e)
    return 80 <= n <= 100 or 350 <= n <= 380


class Splitter:
    """Write rows to name_1.csv, name_2.csv ... each below MAX_BYTES."""

    def __init__(self, base):
        self.base, self.part, self.f, self.w = base, 0, None, None
        self.open_next()

    def open_next(self):
        if self.f:
            self.f.close()
        self.part += 1
        self.f = open(f"{self.base}_{self.part}.csv", "w", newline="")
        self.w = csv.writer(self.f)
        self.w.writerow(["cik", "concept", "start", "end", "val", "filed", "form"])

    def write(self, row):
        if self.f.tell() > MAX_BYTES:
            self.open_next()
        self.w.writerow(row)

    def close(self):
        self.f.close()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for old in os.listdir(OUT_DIR):
        if old.startswith("xbrl_"):
            os.remove(os.path.join(OUT_DIR, old))
    out = {g: Splitter(os.path.join(OUT_DIR, f"xbrl_{g}")) for g in GROUPS}
    counts = {g: 0 for g in GROUPS}
    ciks = 0
    with zipfile.ZipFile(ZIP_PATH) as z:
        for name in sorted(z.namelist()):
            if not name.endswith(".json"):
                continue
            try:
                data = json.loads(z.read(name))
            except Exception as e:
                print(f"skip {name}: {e}", file=sys.stderr)
                continue
            cik = data.get("cik")
            gaap = (data.get("facts") or {}).get("us-gaap") or {}
            hit = False
            for g, concepts in GROUPS.items():
                best = {}  # (start, end) -> (priority, fact, concept code)
                for prio, c in enumerate(concepts):
                    node = gaap.get(c)
                    if not node:
                        continue
                    for unit, facts in (node.get("units") or {}).items():
                        for x in facts:
                            if x.get("form") not in FORMS or "start" not in x:
                                continue
                            if not keep_period(x["start"], x["end"]):
                                continue
                            key = (x["start"], x["end"])
                            cur = best.get(key)
                            cand = (prio, x["filed"])
                            if cur is None or cand < (cur[0], cur[1]["filed"]):
                                best[key] = (prio, x, prio)
                for (s0, e0), (prio, x, code) in sorted(best.items()):
                    out[g].write([cik, code, s0, e0, x["val"], x["filed"], x["form"]])
                    counts[g] += 1
                    hit = True
            ciks += 1 if hit else 0
    for o in out.values():
        o.close()
    print(f"ciks with facts: {ciks}")
    for g in GROUPS:
        print(f"{g}: rows={counts[g]}")
    for fn in sorted(os.listdir(OUT_DIR)):
        print(fn, os.path.getsize(os.path.join(OUT_DIR, fn)))
    with open(os.path.join(OUT_DIR, "xbrl_concepts.txt"), "w") as f:
        for g, concepts in GROUPS.items():
            for i, c in enumerate(concepts):
                f.write(f"{g},{i},{c}\n")


if __name__ == "__main__":
    main()
