"""Save the earnings-related lines of 8-K item 2.02 press releases.

For every item 2.02 filing in a date window, exhibit 99 (the press release)
is downloaded, turned into text (table cells joined with " | ", one table
row per line) and only the lines that matter for EPS and revenue are kept:
headline lines plus lines that mention revenue, sales, earnings, per share,
net income, the period, or the unit ("in thousands"). The parser that turns
these lines into numbers runs later, outside GitHub Actions, so it can be
improved without downloading from SEC again.

Output: one gzip JSON-lines file per run (uploaded as a release asset by
the workflow) and snippets/done.txt (accessions already processed, for
resuming). Stops cleanly after TIME_BUDGET seconds.
"""

import csv
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

UA = os.environ["SEC_CONTACT"]
SRC = "earnings_dates/8k_202.csv"
DONE = "snippets/done.txt"
OUT = os.environ.get("OUT", "/tmp/part.jsonl.gz")
FROM, TO = os.environ.get("FROM", "2004-08-01"), os.environ.get("TO", "2011-12-31")
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", 5 * 3600))
PAUSE = 0.13

KEEP = re.compile(r"revenue|sales|earnings|per share|per diluted|\beps\b|net income|net loss|"
                  r"income \(loss\)|three months|quarter|weeks ended|in thousands|in millions|"
                  r"except per|diluted|basic", re.I)
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


def to_lines(raw, is_html):
    t = raw
    if is_html:
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
        t = re.sub(r"(?is)<table.*?</table>",
                   lambda m: re.sub(r"(?i)</?(p|div|br|font|span)(\s[^>]*)?/?>", " ", m.group(0)), t)
        t = re.sub(r"(?i)<t[dh](\s[^>]*)?>", " | ", t)
        t = re.sub(r"(?i)<tr(\s[^>]*)?>|</tr\s*>|<br\s*/?>|</p\s*>|</div\s*>|</h\d\s*>", "\n", t)
        t = re.sub(r"<[^>]+>", " ", t)
        t = html.unescape(t)
    t = t.replace("\xa0", " ")
    out = []
    for line in t.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        line = re.sub(r"(\|\s*)+\|", "|", line)
        if line and line != "|":
            out.append(line[:300])
    return out


def snippet(cik, acc):
    nod = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nod}/"
    idx = get(base + "index.json")
    files = []
    if idx:
        try:
            names = [it["name"] for it in json.loads(idx)["directory"]["item"]]
            files = [n for n in names if re.search(r"ex[-_v]*99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))]
        except Exception:
            files = []
    lines, src = [], ""
    for n in files[:2]:
        b = get(base + n)
        if b:
            lines += to_lines(b.decode("latin-1", "ignore"), not n.lower().endswith(".txt"))
            src = n
    if not lines:
        b = get(base + acc + ".txt")
        if b:
            t = b.decode("latin-1", "ignore")[:4_000_000]
            lines = to_lines(t, "<table" in t.lower() or "<TABLE" in t)
            src = acc + ".txt"
    head = lines[:30]
    rest = [l for l in lines[30:] if KEEP.search(l)][:400]
    return {"src": src, "head": head, "lines": rest, "n": len(lines)}


def main():
    jobs = []
    with open(SRC) as f:
        for row in csv.DictReader(f):
            if FROM <= row["filing_date"] <= TO:
                jobs.append((row["cik"], row["filing_date"], row["accession"]))
    jobs.sort(key=lambda j: (j[1], j[0]))
    os.makedirs("snippets", exist_ok=True)
    done = set()
    if os.path.exists(DONE):
        done = set(open(DONE).read().split())
    todo = [j for j in jobs if j[2] not in done]
    print(f"filings in window={len(jobs)} done={len(done)} todo={len(todo)}", flush=True)
    t0 = time.time()
    n = 0
    with gzip.open(OUT, "wt") as out, open(DONE, "a") as dn:
        for cik, fdate, acc in todo:
            if time.time() - t0 > TIME_BUDGET:
                print("time budget reached", flush=True)
                break
            s = snippet(cik, acc)
            s.update({"cik": cik, "date": fdate, "acc": acc})
            out.write(json.dumps(s) + "\n")
            dn.write(acc + "\n")
            n += 1
            if n % 1000 == 0:
                dn.flush()
                print(f"{n}/{len(todo)} elapsed={int(time.time()-t0)}s", flush=True)
    print(f"finished this run: processed={n}", flush=True)
    if n < len(todo):
        open("/tmp/more_to_do", "w").write("1")


if __name__ == "__main__":
    sys.exit(main())
