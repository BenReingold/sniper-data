"""Build the SnipeR earnings-announcement date table from SEC EDGAR.

Source: SEC bulk file submissions.zip (all EDGAR filers, nightly). Each
filer's JSON lists its filings with form type, filing date, acceptance
time and, for 8-K filings, the item numbers. An 8-K with item 2.02
("Results of Operations and Financial Condition") is an earnings release.
Item numbers exist from August 2004.

Outputs (CSV, plain text so QuantConnect's download() can read them):
  earnings_dates/8k_202.csv   cik,filing_date,acceptance,form,accession
  earnings_dates/entities.csv cik,name,tickers,exchanges,sic
Only entities with at least one 8-K item 2.02 are written.

Note: SEC's acceptanceDateTime ends in "Z" but is Eastern time. It is
kept as given (without the suffix); the reader converts.
"""

import csv
import io
import json
import os
import sys
import zipfile
from collections import defaultdict

ZIP_PATH = sys.argv[1]
OUT_DIR = sys.argv[2]
FORMS = {"8-K", "8-K/A"}


def rows_from(block):
    """Yield (filing_date, acceptance, form, accession) for 8-K item 2.02."""
    forms = block.get("form", [])
    items = block.get("items", [])
    dates = block.get("filingDate", [])
    acc_times = block.get("acceptanceDateTime", [])
    accs = block.get("accessionNumber", [])
    for i, form in enumerate(forms):
        if form not in FORMS:
            continue
        it = items[i] if i < len(items) else ""
        if "2.02" not in (it or "").split(","):
            continue
        acc_t = acc_times[i] if i < len(acc_times) else ""
        acc_t = (acc_t or "").replace(".000Z", "").replace("Z", "")
        yield dates[i], acc_t, form, accs[i] if i < len(accs) else ""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    events = defaultdict(set)
    entities = {}
    n_files = 0
    with zipfile.ZipFile(ZIP_PATH) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            n_files += 1
            try:
                data = json.loads(z.read(name))
            except Exception as e:  # malformed file: report and skip
                print(f"skip {name}: {e}", file=sys.stderr)
                continue
            base = os.path.basename(name)
            cik = base[3:13]
            if "-submissions-" in base:
                block = data
            else:
                block = data.get("filings", {}).get("recent", {})
                entities[cik] = (
                    data.get("name", ""),
                    "|".join(data.get("tickers", []) or []),
                    "|".join(x or "" for x in (data.get("exchanges", []) or [])),
                    data.get("sic", ""),
                )
            for row in rows_from(block):
                events[cik].add(row)

    path = os.path.join(OUT_DIR, "8k_202.csv")
    n_rows = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cik", "filing_date", "acceptance", "form", "accession"])
        for cik in sorted(events):
            for r in sorted(events[cik]):
                w.writerow([int(cik), *r])
                n_rows += 1

    with open(os.path.join(OUT_DIR, "entities.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cik", "name", "tickers", "exchanges", "sic"])
        for cik in sorted(events):
            w.writerow([int(cik), *entities.get(cik, ("", "", "", ""))])

    years = defaultdict(int)
    for rows in events.values():
        for r in rows:
            years[r[0][:4]] += 1
    print(f"json files read: {n_files}")
    print(f"entities with 8-K item 2.02: {len(events)}")
    print(f"8-K item 2.02 rows: {n_rows}")
    print("rows by year: " + ", ".join(f"{y}:{years[y]}" for y in sorted(years)))
    print(f"8k_202.csv bytes: {os.path.getsize(path)}")


if __name__ == "__main__":
    main()
