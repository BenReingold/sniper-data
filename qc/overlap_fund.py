from AlgorithmImports import *
from sniper_data import SniperData
import statistics as stats

PAIRS = [("H003", "H132su"), ("H005", "H132su"), ("H029", "H132su"), ("H029", "H120"),
         ("H004", "H128"), ("H003", "H004"), ("H034", "H089")]


class SnipeROverlapFund(QCAlgorithm):
    """Overlap (symmetric Jaccard of stock-date sets) for the D1/D2/D8 pairs
    that the freeze requires before waves 2 and 1b, using the data module.
    Quarter-end samples 2005-2018, U0. Filters are states on the sample day.
    Not a trial (no forward returns).
    Definitions (SnipeR codings; [S] where the card leaves a detail open):
    H003 EPS yoy >= 25% (prior > 0); H004 revenue yoy >= 25%;
    H005 EPS yoy growth rising over the last 3 quarters;
    H029 SUE on EPS (diff vs year-ago quarter / sd of last 8 diffs), top decile;
    H132su saleq_su on revenue (diff minus mean of last 8 diffs, / their sd), top tercile;
    H120 3-day return around the last announcement (t-1..t+1, minus SPY) within
    the last 126 sessions, top decile of those with an announcement;
    H128 (at_gr1 only) total assets growth 1 year, lowest tercile (Morningstar);
    H034 d1 industry group mean 126-session return, top 30% of groups;
    H089 3+ industry-group peers among the top 20 U0 stocks by 20-session return [S]."""

    def initialize(self):
        self.set_start_date(2004, 1, 1)
        self.set_end_date(2018, 12, 31)
        self.set_cash(100000)
        self.sd = SniperData(self)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.add_universe(self.sel)
        self.sets = {}
        self.last_q = None
        self.info = {}

    def sel(self, fundamental):
        u = self.sd.u0(fundamental)
        t = self.time
        q = (t.year, (t.month - 1) // 3)
        if t.year < 2005 or q == self.last_q or t.month not in (3, 6, 9, 12) or t.day < 20:
            return []
        self.last_q = q
        fmap = {f.symbol: f for f in fundamental}
        self.sample(u, fmap)
        return []

    def sue(self, qs, field):
        vals = [x[field] for x in qs if x[field] is not None]
        if len(vals) < 12:
            return None
        diffs = [vals[i] - vals[i + 4] for i in range(len(vals) - 4)]
        if len(diffs) < 9:
            return None
        hist = diffs[1:9]
        sd = stats.pstdev(hist)
        if sd == 0:
            return None
        return diffs[0], sd, stats.mean(hist)

    def sample(self, u, fmap):
        d = self.time.date()
        S = {k: set() for k in ("H003", "H004", "H005", "H029", "H132su", "H120", "H128", "H034", "H089")}
        sue_e, sue_r, ann_ret, at_gr = {}, {}, {}, {}
        hist = self.history(u + [self.spy], 140, Resolution.DAILY)
        close = hist["close"].unstack(0) if not hist.empty else None
        for s in u:
            qs = self.sd.quarters(s, 13)
            # keep only quarters with a period end (XBRL) or announcement order (press)
            if qs:
                g = self.sd.yoy(s, "eps")
                if g is not None and qs[0]["eps_prev"] is not None and qs[0]["eps_prev"] > 0 and g >= 0.25:
                    S["H003"].add(s)
                gr = self.sd.yoy(s, "revenue")
                if gr is not None and gr >= 0.25:
                    S["H004"].add(s)
                e = [x["eps"] for x in qs]
                if len(e) >= 7 and all(v is not None for v in e[:7]):
                    gs = []
                    for i in range(3):
                        b = e[i + 4]
                        gs.append(None if not b or b <= 0 else e[i] / b - 1)
                    if None not in gs and gs[0] > gs[1] > gs[2]:
                        S["H005"].add(s)
                se = self.sue(qs, "eps")
                if se:
                    sue_e[s] = se[0] / se[1]
                sr = self.sue(qs, "revenue")
                if sr:
                    sue_r[s] = (sr[0] - sr[2]) / sr[1]
            ds = self.sd.days_since_announcement(s)
            if ds is not None and ds <= 180 and close is not None and s in close.columns:
                ad = d.toordinal() - ds
                col, spyc = close[s].dropna(), close[self.spy].dropna()
                idx = [i for i, ts in enumerate(col.index) if ts.date().toordinal() >= ad]
                if idx and idx[0] >= 2 and idx[0] + 1 < len(col):
                    i0 = idx[0]
                    t0, t1 = col.index[i0 - 2], col.index[i0 + 1]
                    if t0 in spyc.index and t1 in spyc.index:
                        ann_ret[s] = col[t1] / col[t0] - spyc[t1] / spyc[t0]
            f = fmap.get(s)
            if f is not None:
                try:
                    ta = f.financial_statements.balance_sheet.total_assets
                    now = ta.three_months
                    hist_vals = self.info.setdefault(s, [])
                    if now and now == now:
                        hist_vals.append((d.toordinal(), now))
                        old = [v for o, v in hist_vals if 330 <= d.toordinal() - o <= 400]
                        if old and old[0] > 0:
                            at_gr[s] = now / old[0] - 1
                except Exception:
                    pass

        def top(dct, share, low=False):
            if not dct:
                return set()
            ks = sorted(dct, key=lambda k: dct[k], reverse=not low)
            return set(ks[:max(1, int(len(ks) * share))])
        S["H029"] = top(sue_e, 0.10)
        S["H132su"] = top(sue_r, 1 / 3)
        S["H120"] = top(ann_ret, 0.10)
        S["H128"] = top(at_gr, 1 / 3, low=True)
        # industry filters
        if close is not None:
            r126, r20, grp = {}, {}, {}
            for s in u:
                if s not in close.columns:
                    continue
                c = close[s].dropna()
                if len(c) >= 127:
                    r126[s] = c.iloc[-1] / c.iloc[-127] - 1
                if len(c) >= 21:
                    r20[s] = c.iloc[-1] / c.iloc[-21] - 1
                f = fmap.get(s)
                try:
                    g = f.asset_classification.morningstar_industry_group_code if f else None
                except Exception:
                    g = None
                if g:
                    grp[s] = g
            gm = {}
            for s, g in grp.items():
                if s in r126:
                    gm.setdefault(g, []).append(r126[s])
            gmean = {g: stats.mean(v) for g, v in gm.items() if len(v) >= 3}
            topg = top(gmean, 0.30)
            S["H034"] = {s for s, g in grp.items() if g in topg}
            leaders = sorted(r20, key=lambda k: r20[k], reverse=True)[:20]
            cnt = {}
            for s in leaders:
                if s in grp:
                    cnt[grp[s]] = cnt.get(grp[s], 0) + 1
            S["H089"] = {s for s in leaders if s in grp and cnt[grp[s]] >= 3}
        for k, v in S.items():
            self.sets.setdefault(k, set()).update((s, d) for s in v)
        self.log(f"OVF {d} u0={len(u)} " + " ".join(f"{k}={len(v)}" for k, v in S.items()))

    def on_end_of_algorithm(self):
        for a, b in PAIRS:
            A, B = self.sets.get(a, set()), self.sets.get(b, set())
            ab = len(A & B)
            j = ab / max(len(A | B), 1)
            self.log(f"OVERLAP {a} vs {b}: nA={len(A)} nB={len(B)} nAB={ab} jaccard={j:.3f} "
                     f"A_in_B={ab / max(len(A), 1):.3f} B_in_A={ab / max(len(B), 1):.3f}")
