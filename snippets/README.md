# Press-release snippets

Release "snippets" holds one gzip JSON-lines file per scan run
(scripts/scan_snippets.py, workflow scan_snippets.yml). Each line:
cik, date, acc, src (exhibit file), head (first 30 lines), lines (keyword
lines plus the two lines after each), n (total lines).

Parts from test runs with earlier parser versions are invalid and must be
skipped: part_20261114_082203, part_20261114_082425, part_20261114_083206,
part_20261114_083535, part_20261114_084324. Valid parts start with the run
of commit 599e12d (2026-11-14, after 08:45 UTC).
