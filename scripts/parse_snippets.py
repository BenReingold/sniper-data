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
                     r"special|items|segment|dividend|book value|funds from operations|\bffo\b|"
                     r"reconcil|outstanding|comparable|\bcore\b|recurring|normaliz|%", re.I)
QTR_H = re.compile(r"three months|3 months|quarter|13 weeks|12 weeks|14 weeks|sixteen weeks|16 weeks|\bq[1-4]\b", re.I)
YTD_H = re.compile(r"six months|nine months|twelve months|6 months|9 months|12 months|year ended|years ended|"
                   r"fiscal year|full year|year to date|year-to-date|26 weeks|39 weeks|52 weeks|53 weeks|"
                   r"twenty-six|thirty-nine|fifty-two", re.I)
YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
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


NARR = re.compile(r"(revenues?|sales)[^.$]{0,80}?\$\s?(\d[\d,]*\.?\d*)\s*(thousand|million|billion)", re.I)
NARR_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9}


def unit_from_text(lines, value):
    """Pick the unit that makes the table value match a revenue amount quoted
    in the release text (for example "net sales of $626.0 million")."""
    seen = False
    for line in lines:
        for m in NARR.finditer(line):
            seen = True
            try:
                amt = float(m.group(2).replace(",", "")) * NARR_SCALE[m.group(3).lower()]
            except ValueError:
                continue
            for u, k in (("thousands", 1e3), ("millions", 1e6), ("billions", 1e9), ("", 1.0)):
                if amt and abs(value * k - amt) <= 0.02 * amt:
                    return u
    return "MISMATCH" if seen else None


NARR_EPS = re.compile(r"\$\s?\(?(\d+\.\d{2})\)?\s*(?:per diluted share|per share,? diluted|diluted earnings per share|per diluted common share)|"
                      r"diluted (?:earnings|eps|net income|income|loss)[^.$]{0,50}?\$\s?\(?(\d+\.\d{2})", re.I)


def eps_check(lines, value):
    quoted = set()
    for line in lines:
        for m in NARR_EPS.finditer(line):
            quoted.add(float(m.group(1) or m.group(2)))
    if not quoted:
        return None
    return any(abs(abs(value) - q) <= 0.005 for q in quoted)


def eps_check_any(lines, values):
    """True when the text quotes a diluted EPS that equals another diluted
    row of the same column (for example continuing operations): the column
    choice is then confirmed."""
    return any(eps_check(lines, v) for v in values)


def parse(rec):
    lines = rec.get("head", []) + rec.get("lines", [])
    eps = rev = eps2 = rev2 = None
    eps_label = rev_label = ""
    unit, unit_line = None, -999
    unit_at_rev = None
    eps_ctx = 0      # rows since a "per share" header
    cont_ctx = 0     # rows since a "continuing operations" header
    years_desc = True
    diluted_cols = set()  # current-column values of every diluted per-share row (incl. continuing ops)
    block = 0        # which pair of numbers holds the quarter: 0 = first pair, 1 = second pair
    annual_only = False
    for idx, line in enumerate(lines):
        um = UNIT.search(line)
        if um:
            unit = (um.group(1) or um.group(2) or "thousands").lower()
            unit_line = idx
        label, nums = split_row(line)
        low = label.lower()
        # period header: decides whether the quarter columns come first, second, or not at all
        qm, ym = QTR_H.search(line), YTD_H.search(line)
        if (qm or ym) and all(1980 <= abs(v) <= 2039 or (v == int(v) and 0 < v <= 53) for v in nums):
            if qm and ym:
                block, annual_only = (0 if qm.start() < ym.start() else 1), False
            elif qm:
                block, annual_only = 0, False
            else:
                block, annual_only = 0, True
            continue
        # header rows with two or more years and no other numbers set the column order
        yrs = [int(y) for y in YEAR.findall(line)]
        if len(yrs) >= 2 and all(1980 <= abs(v) <= 2039 for v in nums):
            years_desc = yrs[0] >= yrs[1]
            continue
        if re.search(r"continuing operations", low) and not nums:
            cont_ctx = 4
        elif cont_ctx:
            cont_ctx -= 1
        if re.search(r"(earnings|income|loss).{0,30}per (common |diluted )?share|^eps\b|per share data", low) and not nums:
            eps_ctx = 6
        elif eps_ctx:
            eps_ctx -= 1
        if not nums:
            continue
        if annual_only:
            continue
        pair = nums[2 * block:2 * block + 2] if len(nums) >= 2 * block + 1 else []
        if not pair:
            continue
        cur = pair[0] if years_desc or len(pair) < 2 else pair[1]
        prv = (pair[1] if years_desc else pair[0]) if len(pair) > 1 else None
        is_table = "|" in line or len(nums) >= 2
        if is_table and "diluted" in low and ("per" in low or "share" in low) and abs(cur) < 100:
            diluted_cols.add(round(abs(cur), 2))
        narrative = (len(label) > 70 or
                     re.search(r"expect|guidance|outlook|quarter of|year of|20\d\d|reports|reported", low) or
                     re.search(r"\b(were|was|of|totaled|increased|decreased|compared)$", low))
        if (eps is None and is_table and not narrative and "diluted" in low and not EPS_BAD.search(low)
                and not cont_ctx):
            if ("per" in low or "share" in low or "eps" in low or eps_ctx) and abs(cur) < 100:
                eps, eps2, eps_label = cur, prv, label[:60]
        if rev is None and is_table and REV_ROW.match(low.strip()):
            if abs(cur) >= 1:
                rev, rev2, rev_label = cur, prv, label[:60]
                unit_at_rev = unit
    if eps is not None and eps_check(lines, eps) is False and not eps_check_any(lines, diluted_cols):
        # the text quotes diluted EPS figures and none equals the table row: drop it
        eps = eps2 = None
        eps_label = ""
    if rev is not None:
        u = unit_from_text(lines, abs(rev))
        if u == "MISMATCH":
            # the text quotes revenue amounts but none equals the table row:
            # the row is probably not total revenue for the quarter; drop it
            rev = rev2 = None
            rev_label = ""
        elif u is not None:
            unit_at_rev = u
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
