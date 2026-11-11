"""Extract quarterly and annual income facts from SEC companyfacts.zip.

Source: SEC bulk file companyfacts.zip (XBRL facts of all filers, from 2009).
For each CIK and each concept below, every reported value is kept once per
(period start, period end) at its FIRST filing (point in time: what was known
then), with the filing date and form. Restated values filed later are kept in
a separate file so that tests can use first-reported numbers only.

Outputs (CSV, one per concept group, plain text for QuantConnect):
  fundamentals/xbrl_eps.csv      cik,concept,start,end,val,filed,form,accn
  fundamentals/xbrl_revenue.csv  same columns
  fundamentals/xbrl_netincome.csv
"""

import csv
import json
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    writers, files = {}, {}
    for g in GROUPS:
        f = open(os.path.join(OUT_DIR, f"xbrl_{g}.csv"), "w", newline="")
        w = csv.writer(f)
        w.writerow(["cik", "concept", "start", "end", "val", "filed", "form", "accn"])
        writers[g], files[g] = w, f
    counts = {g: 0 for g in GROUPS}
    ciks = 0
    with zipfile.ZipFile(ZIP_PATH) as z:
        for name in z.namelist():
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
                for c in concepts:
                    node = gaap.get(c)
                    if not node:
                        continue
                    for unit, facts in (node.get("units") or {}).items():
                        first = {}
                        for x in facts:
                            if x.get("form") not in FORMS or "start" not in x:
                                continue
                            key = (x["start"], x["end"])
                            if key not in first or x["filed"] < first[key]["filed"]:
                                first[key] = x
                        for (s, e), x in sorted(first.items()):
                            writers[g].writerow([cik, c, s, e, x["val"], x["filed"], x["form"], x.get("accn", "")])
                            counts[g] += 1
                            hit = True
            ciks += 1 if hit else 0
    for f in files.values():
        f.close()
    print(f"ciks with facts: {ciks}")
    for g in GROUPS:
        p = os.path.join(OUT_DIR, f"xbrl_{g}.csv")
        print(f"{g}: rows={counts[g]} bytes={os.path.getsize(p)}")


if __name__ == "__main__":
    main()
