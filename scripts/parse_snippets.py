"""Turn press-release snippets into quarterly diluted EPS and revenue.

Input: gzip JSON-lines parts of release "snippets" (see snippets/README.md).
Output: CSV cik,date,acc,eps,eps_label,revenue,rev_label,unit.
The first matching row is used; the first number in a row is taken as the
current period (earnings tables put the current quarter first).
Usage: parse_snippets.py OUT.csv PART.gz [PART.gz ...]
"""

import csv
import gzip
import json
import re
import sys

NUM = re.compile(r"\(?-?\$?\s?\d[\d,]*\.?\d*\)?|\(?-?\$?\s?\.\d+\)?")
DASH = re.compile(r"^[—–\-]+$")
EPS_BAD = re.compile(r"continu|discontinu|adjust|non-?gaap|pro ?forma|operating|excluding|"
                     r"weighted|shares|guidance|outlook|estimate|before|cumulative|"
                     r"special|items|segment|dividend|book value|%", re.I)
REV_ROW = re.compile(r"^(total |consolidated )?(net )?(operating )?(revenues?|sales)(,? net)?"
                     r"( and other income)?\s*:?$|^revenues?,? net$|^net sales and revenues?$|"
                     r"^total (net )?(revenues?|sales)$", re.I)
UNIT = re.compile(r"(?:in|\$|\$ in|dollars in|amounts in|expressed in)\s*(thousands|millions|billions)|(thousands|millions|billions) of|\((000)'?s?\)|(000)'?s omitted", re.I)
SCALE = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}


def to_num(tok):
    t = tok.strip()
    neg = t.startswith("(") or t.startswith("-")
    t = t.strip("()$- ").replace(",", "")
    if not t or t == ".":
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def split_row(line):
    """Return (label, [numbers]) for a table or text row."""
    if "|" in line:
        cells = [c.strip() for c in line.split("|")]
        label_parts, nums = [], []
        open_paren = False
        for c in cells:
            if c in ("(", "$(", "($"):
                open_paren = True
                continue
            if c in (")", ")%"):
                continue
            if open_paren and c and c[0].isdigit():
                c = "(" + c
            open_paren = False
            if not c or c == "$" or DASH.match(c):
                if DASH.match(c or "x") and label_parts:
                    nums.append(0.0)
                continue
            m = NUM.fullmatch(c.replace(" ", ""))
            if m and any(ch.isdigit() for ch in c):
                v = to_num(c)
                if v is not None:
                    nums.append(v)
                    continue
            if not nums:
                label_parts.append(c)
        return " ".join(label_parts).strip(" :.$"), nums
    m = re.search(r"(\s{2,}|\.{3,}|\$)\s*\(?-?\$?\s?\d", line)
    if not m:
        return line.strip(), []
    label = line[:m.start()].strip(" :.$")
    nums = [to_num(x) for x in NUM.findall(line[m.start():])]
    return label, [v for v in nums if v is not None]


def parse(rec):
    lines = rec.get("head", []) + rec.get("lines", [])
    eps = rev = eps2 = rev2 = None
    eps_label = rev_label = ""
    unit = None
    unit_at_rev = None
    eps_ctx = 0  # rows since a "per share" header
    for line in lines:
        um = UNIT.search(line)
        if um:
            unit = (um.group(1) or um.group(2) or "thousands").lower()
        label, nums = split_row(line)
        low = label.lower()
        if re.search(r"(earnings|income|loss).{0,30}per (common |diluted )?share|^eps\b|per share data", low) and not nums:
            eps_ctx = 6
        elif eps_ctx:
            eps_ctx -= 1
        is_table = "|" in line or len(nums) >= 2
        narrative = len(label) > 70 or re.search(r"expect|guidance|outlook|quarter of|year of|20\d\d|reports|reported", low)
        if eps is None and nums and is_table and not narrative and "diluted" in low and not EPS_BAD.search(low):
            if ("per" in low or "share" in low or "eps" in low or eps_ctx) and abs(nums[0]) < 1000:
                eps, eps_label = nums[0], label[:60]
                eps2 = nums[1] if len(nums) > 1 else None
        if rev is None and nums and is_table and REV_ROW.match(low.strip()):
            if abs(nums[0]) >= 1:
                rev, rev_label, unit_at_rev = nums[0], label[:60], unit
                rev2 = nums[1] if len(nums) > 1 else None
    return eps, eps_label, rev, rev_label, unit_at_rev, eps2, rev2


def main():
    out = sys.argv[1]
    n = ne = nr = 0
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cik", "date", "acc", "eps", "eps_label", "revenue", "rev_label", "unit", "eps_prev", "rev_prev"])
        for part in sys.argv[2:]:
            for line in gzip.open(part, "rt"):
                rec = json.loads(line)
                eps, el, rev, rl, unit, e2, r2 = parse(rec)
                w.writerow([rec["cik"], rec["date"], rec["acc"],
                            "" if eps is None else eps, el,
                            "" if rev is None else rev, rl, unit or "",
                            "" if e2 is None else e2, "" if r2 is None else r2])
                n += 1
                ne += eps is not None
                nr += rev is not None
    print(f"filings={n} eps_found={ne} ({ne/n:.1%}) revenue_found={nr} ({nr/n:.1%})")


if __name__ == "__main__":
    main()
