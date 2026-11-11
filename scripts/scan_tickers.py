"""Extract the stock ticker from 8-K item 2.02 press releases.

For each CIK in earnings_dates/8k_202.csv, the first and the last item 2.02
filing are opened; exhibit 99 (the press release) is searched for patterns
like "(NYSE: LEH)". Output: earnings_dates/cik_tickers.csv with
cik,filing_date,accession,exchange,ticker,hits (one row per filing; ticker
empty when none found). The run is resumable: filings already in the output
are skipped. Stops cleanly after TIME_BUDGET seconds.
"""

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

UA = os.environ["SEC_CONTACT"]
SRC = "earnings_dates/8k_202.csv"
OUT = "earnings_dates/cik_tickers.csv"
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", 5 * 3600))
PAUSE = 0.13  # about 7 requests per second, under SEC's 10 per second

EXCH = r"(NYSE American|NYSE Amex|NYSE MKT|NYSE Arca|NYSE|Nasdaq[A-Za-z /]{0,32}?|NASDAQ[A-Za-z /]{0,32}?|AMEX|American Stock Exchange|New York Stock Exchange)"
PAT = re.compile(EXCH + r"\s*[:\-]\s*([A-Z]{1,5}(?:\.[A-Z])?)\b")

last_call = [0.0]


def get(url):
    for attempt in range(5):
        wait = PAUSE - (time.time() - last_call[0])
        if wait > 0:
            time.sleep(wait)
        last_call[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** attempt * 2)
        except Exception:
            time.sleep(2 ** attempt)
    return None


def ticker_from(cik, acc):
    nod = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nod}/"
    idx = get(base + "index.json")
    files = []
    if idx:
        try:
            items = json.loads(idx)["directory"]["item"]
            names = [it["name"] for it in items]
            files = [n for n in names if re.search(r"ex[-_]?99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))]
        except Exception:
            files = []
    texts = []
    for n in files[:2]:
        b = get(base + n)
        if b:
            texts.append(b.decode("latin-1", "ignore"))
    if not texts:
        b = get(base + acc + ".txt")
        if b:
            texts.append(b.decode("latin-1", "ignore")[:3_000_000])
    c = Counter()
    for t in texts:
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"&nbsp;|&#160;|\s+", " ", t)
        for ex, tk in PAT.findall(t):
            c[(ex.strip().split()[0].upper(), tk)] += 1
    if not c:
        return "", "", 0
    (ex, tk), n = c.most_common(1)[0]
    return ex, tk, n


def main():
    first, last = {}, {}
    with open(SRC) as f:
        for row in csv.DictReader(f):
            k = row["cik"]
            item = (row["filing_date"], row["accession"])
            if k not in first or item < first[k]:
                first[k] = item
            if k not in last or item > last[k]:
                last[k] = item
    jobs = []
    if os.environ.get("MODE") == "yearly":
        per_year = {}
        with open(SRC) as f:
            for row in csv.DictReader(f):
                key = (row["cik"], row["filing_date"][:4])
                item = (row["filing_date"], row["accession"])
                if key not in per_year or item < per_year[key]:
                    per_year[key] = item
        for (k, _), item in sorted(per_year.items(), key=lambda x: (int(x[0][0]), x[0][1])):
            jobs.append((k, *item))
    else:
        for k in sorted(first, key=int):
            jobs.append((k, *first[k]))
            if last[k] != first[k]:
                jobs.append((k, *last[k]))
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            done = {r["accession"] for r in csv.DictReader(f)}
    todo = [j for j in jobs if j[2] not in done]
    print(f"filings total={len(jobs)} done={len(done)} todo={len(todo)}", flush=True)
    new = not os.path.exists(OUT)
    t0 = time.time()
    found = 0
    with open(OUT, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["cik", "filing_date", "accession", "exchange", "ticker", "hits"])
        for i, (cik, fdate, acc) in enumerate(todo):
            if time.time() - t0 > TIME_BUDGET:
                print("time budget reached", flush=True)
                break
            ex, tk, n = ticker_from(cik, acc)
            found += 1 if tk else 0
            w.writerow([cik, fdate, acc, ex, tk, n])
            if i % 500 == 0:
                f.flush()
                print(f"{i}/{len(todo)} found={found} elapsed={int(time.time()-t0)}s", flush=True)
    print(f"finished this run: processed={i + 1 if todo else 0} found={found}", flush=True)
    if todo and i + 1 < len(todo):
        open("/tmp/more_to_do", "w").write("1")


if __name__ == "__main__":
    sys.exit(main())
