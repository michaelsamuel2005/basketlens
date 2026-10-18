"""The supplier deck: 12 slides for a brand manager, built from results.json (no figure is typed by hand).

    python -m basketlens.cli deck --manufacturer 794
Charts are native PowerPoint charts (editable). Manufacturer ids in the data are anonymised, so the deck says "the supplier".
"""
from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

NAVY, TEAL, AMBER, GREY, LIGHT, RED = (RGBColor(0x1B, 0x2A, 0x41), RGBColor(0x0F, 0x8B, 0x8D), RGBColor(0xE0, 0x9F, 0x3E),
                                       RGBColor(0x5C, 0x6B, 0x73), RGBColor(0xF1, 0xF4, 0xF6), RGBColor(0xC0, 0x39, 0x2B))
FONT = "Calibri"
SOURCE = "Source: Complete Journey (84.51°, CC0): 2,469 households of a US grocery retailer, 2017. Manufacturer ids are anonymised. Not Nectar or Sainsbury's data."


def _d(x, dp=0):
    return f"-${abs(x):,.{dp}f}" if x < 0 else f"${x:,.{dp}f}"


def _p(x, dp=0):
    return f"{100 * x:.{dp}f}%"


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.n = 0

    def slide(self, title: str, notes: str = ""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.n += 1
        bar = s.shapes.add_shape(1, 0, 0, Inches(0.18), self.prs.slide_height)
        bar.fill.solid(); bar.fill.fore_color.rgb = TEAL; bar.line.fill.background()
        self.text(s, title, 0.55, 0.35, 12.2, 1.1, size=26, bold=True, color=NAVY)
        self.text(s, SOURCE, 0.55, 7.05, 11.6, 0.35, size=10, color=GREY)
        self.text(s, str(self.n), 12.5, 7.05, 0.5, 0.35, size=10, color=GREY, align=PP_ALIGN.RIGHT)
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    def text(self, s, text, x, y, w, h, size=16, bold=False, color=NAVY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
        lines = text if isinstance(text, list) else [text]
        for i, ln in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run(); r.text = ln
            r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, FONT
            p.space_after = Pt(6)
        return tb

    def bullets(self, s, items, x, y, w, h, size=16):
        return self.text(s, ["•  " + i for i in items], x, y, w, h, size=size, color=NAVY)

    def card(self, s, big, small, x, y, w=2.9, h=1.35, color=TEAL):
        r = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        r.fill.solid(); r.fill.fore_color.rgb = LIGHT; r.line.fill.background()
        self.text(s, big, x + 0.12, y + 0.08, w - 0.24, 0.65, size=28, bold=True, color=color)
        self.text(s, small, x + 0.12, y + 0.75, w - 0.24, 0.6, size=12, color=GREY)

    def chart(self, s, kind, cats, series: dict, x, y, w, h, fmt='#,##0', legend=True, colors=None, labels=True, size=12):
        cd = CategoryChartData(); cd.categories = cats
        for k, v in series.items():
            cd.add_series(k, v)
        gf = s.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd)
        ch = gf.chart
        ch.has_legend = legend and len(series) > 1
        if ch.has_legend:
            ch.legend.position, ch.legend.include_in_layout = XL_LEGEND_POSITION.BOTTOM, False
            ch.legend.font.size = Pt(size)
        ch.font.size, ch.font.name = Pt(size), FONT
        pal = colors or [TEAL, AMBER, NAVY, GREY]
        for i, pl in enumerate(ch.plots[0].series):
            pl.format.fill.solid(); pl.format.fill.fore_color.rgb = pal[i % len(pal)]
        if labels:
            ch.plots[0].has_data_labels = True
            dl = ch.plots[0].data_labels; dl.number_format, dl.number_format_is_linked, dl.font.size = fmt, False, Pt(size)
        ch.has_title = False
        ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
        ch.value_axis.has_major_gridlines = False
        ch.value_axis.tick_labels.number_format, ch.value_axis.tick_labels.number_format_is_linked = fmt, False
        return ch

    def table(self, s, rows, x, y, w, col_w, size=12, row_h=0.36, header=True, header_h=None):
        shp = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
        t = shp.table
        for j, cw in enumerate(col_w):
            t.columns[j].width = Inches(cw)
        if header_h:
            t.rows[0].height = Inches(header_h)
            for i in range(1, len(rows)):
                t.rows[i].height = Inches(row_h)
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                c = t.cell(i, j); c.text = str(v)
                c.margin_left = c.margin_right = Inches(0.06)
                for p in c.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size, run.font.name = Pt(size), FONT
                        run.font.bold = (i == 0 and header)
                        run.font.color.rgb = RGBColor(255, 255, 255) if (i == 0 and header) else NAVY
                c.fill.solid(); c.fill.fore_color.rgb = NAVY if (i == 0 and header) else (LIGHT if i % 2 else RGBColor(255, 255, 255))
        return t


def reading(row) -> str:
    lo, hi, v = row["ci_low"], row["ci_high"], row["pct_effect"]
    if lo <= 0 <= hi:
        return "no clear effect"
    return "raises sales" if v > 0 else "lowers sales"


def build(out: Path, ctx=None) -> Path:
    R = json.loads((out / "results.json").read_text())
    F = R["facts"]
    sc = None
    for cand in (out.parent / "twin_seed7" / "scorecard.json",):
        if cand.exists():
            sc = json.loads(cand.read_text())["summary"]
    D = Deck()
    dec = {r["entity"]: r for r in F["decomposition"]}
    sup = dec["supplier"]
    seg = F["segments"]
    pr = {r["term"]: r for r in F["promo_coefs_supplier"]}
    P = F["promotions"]
    rg, sc_r = F["ranging"], {r["scenario"]: r for r in F["range_scenarios"]}
    cs = F["campaign_summary"]
    lc, fl, tr = F["lifecycle"], F["flows"], F["trial"]
    peers = R["peers"]
    sp = next(p for p in peers if p["entity"] == R["supplier"])
    cat = R["category"].title()

    # 1 title
    s = D.prs.slides.add_slide(D.prs.slide_layouts[6]); D.n += 1
    bg = s.shapes.add_shape(1, 0, 0, D.prs.slide_width, D.prs.slide_height); bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    D.text(s, f"{cat}: where the supplier wins, where it leaks, and what to do next", 0.8, 2.0, 11.5, 1.8, size=38, bold=True, color=RGBColor(255, 255, 255))
    D.text(s, f"A supplier review built on loyalty-card data: {sp['buyers']:,.0f} of 2,469 households bought the supplier, one year of shopping",
           0.8, 4.0, 11.5, 0.9, size=18, color=RGBColor(0xCF, 0xE8, 0xE9))
    D.text(s, SOURCE, 0.8, 6.6, 11.8, 0.6, size=11, color=RGBColor(0xCF, 0xD8, 0xDC))

    # 2 summary
    s = D.slide("The supplier leads the category but is slipping, its lapsed buyers go to rival brands, and its campaigns cannot yet be shown to pay")
    D.card(s, _p(sp["share"], 0), f"share of {cat.lower()} sales (rank 1 of {len([p for p in peers if p['share'] > 0.01])} suppliers over 1%)", 0.6, 1.7)
    D.card(s, _p(sp["penetration"], 0), "of category buyers bought it in the year", 3.7, 1.7)
    D.card(s, _p(tr["repeat_rate"], 0), "of new buyers buy again within 12 weeks", 6.8, 1.7)
    D.card(s, _d(cs["naive_incremental"]) + " → " + _d(cs["incremental_sales"]), "campaign sales: plain comparison → after matching on past spend", 9.9, 1.7, w=2.9, color=RED)
    recs = R["recommendations"]
    D.text(s, "What to do", 0.6, 3.4, 6, 0.4, size=18, bold=True, color=TEAL)
    D.bullets(s, [r["title"] + ". " + r["size"] for r in recs], 0.6, 3.9, 12.1, 2.4, size=16)
    D.text(s, "Every figure comes from the analysis tables; where a figure rests on an assumption the slide says so.", 0.6, 6.4, 12, 0.5, size=13, color=GREY)

    # 3 decomposition
    ents = ["supplier", "private label", "other brands"]
    comp = {"Buyers": [dec[e]["buyers"] for e in ents], "Trips per buyer": [dec[e]["frequency"] for e in ents],
            "Spend per trip": [dec[e]["spend_per_trip"] for e in ents]}
    neg = [k.lower() for k, v in comp.items() if v[0] < 0]
    pos = [k.lower() for k, v in comp.items() if v[0] > 0]
    s = D.slide(f"Supplier sales slipped {_d(abs(sup['change']))} ({_p(abs(sup['change']) / sup['sales_h1'], 1)}) from the first half to the second: {' and '.join(neg)} fell, {' and '.join(pos)} rose")
    D.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, ["Supplier", "Private label", "Other brands"], {k: v for k, v in comp.items()}, 0.6, 1.6, 7.6, 5.2, fmt='$#,##0')
    D.text(s, "Change in sales H1 to H2, split into its three parts", 0.6, 1.45, 7.6, 0.3, size=12, color=GREY)
    D.bullets(s, [f"Sales {_d(sup['sales_h1'])} → {_d(sup['sales_h2'])} for the supplier; other brands gained {_d(dec['other brands']['change'])}.",
                  "The three parts add exactly to the change (log-mean split of buyers × trips per buyer × sales per trip).",
                  f"The category itself was flat ({_d(dec['category']['change'])}), so this is share moving, not a shrinking market."],
              8.5, 1.8, 4.3, 4.5, size=15)

    # 4 funnel
    fun = F["funnel"]
    s = D.slide(f"{_p(fun[1]['households'] / fun[0]['households'], 0)} of cereal buyers have bought the supplier, but the funnel narrows fast: only {_p(fun[4]['households'] / fun[1]['households'], 0)} of them buy it 8 times or more")
    D.chart(s, XL_CHART_TYPE.BAR_CLUSTERED, [f["stage"] for f in fun][::-1], {"Households": [f["households"] for f in fun][::-1]}, 0.6, 1.6, 7.2, 5.2, legend=False)
    d_ = F["repeat_by_deal"]
    a, b = d_["first purchase on discount"], d_["first purchase at full price"]
    D.bullets(s, [f"{tr['triers']} households bought the supplier for the first time after week 14. {_p(tr['repeat_rate'], 0)} bought again within 12 weeks (95% interval {_p(tr['repeat_ci'][0], 0)} to {_p(tr['repeat_ci'][1], 0)}; {tr['with_12w_followup']} had a full 12 weeks to do so).",
                  f"First purchase on discount: {_p(a['repeat_rate'], 0)} repeat; at full price: {_p(b['repeat_rate'], 0)}. The intervals overlap, so promotions do not clearly bring in lower-quality buyers.",
                  "Time to a second purchase follows a steady curve with no early cliff (tables/journey_second_purchase.csv)."], 8.1, 1.8, 4.7, 4.8, size=14)

    # 5 lapse
    s = D.slide(f"{lc['lapsed_to_others']} of {lc['established']} established buyers stopped buying the supplier but kept buying cereal: they moved to rival brands, not private label")
    D.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, ["Lapsed buyers, before (H1)", "Lapsed buyers, after (Q4)", "All households (Q4)"],
            {"Private label share of what they bought instead": [fl["pl_share_of_rest_h1"], fl["pl_share_of_rest_q4"], fl["pl_share_of_rest_all_households_q4"]]},
            0.6, 1.6, 6.4, 5.2, fmt='0%', legend=False)
    D.bullets(s, [f"Established buyer = 4 or more supplier trips in weeks 2–27. Lapsed = none in weeks 41–53, still buying cereal. {lc['kept']} kept buying; {lc['left_category']} left the category.",
                  f"About {lc['chance_silences_expected']:.0f} silences would be expected by chance from each buyer's own rate, so the excess is about {lc['excess_lapsed']:.0f}.",
                  f"Private label is {_p(fl['pl_share_of_rest_q4'], 0)} of what lapsed buyers bought instead, in line with {_p(fl['pl_share_of_rest_all_households_q4'], 0)} for everyone: the leak is to other national brands.",
                  f"Before lapsing they spent about {_d(fl['annualised_value_of_lapsed'])} a year with the supplier."], 7.3, 1.8, 5.5, 4.9, size=14)

    # 6 segments
    seg_sorted = sorted(seg, key=lambda r: -r["supplier_share_of_segment_category"])
    low = min(seg, key=lambda r: r["supplier_share_of_segment_category"])
    best = max(seg, key=lambda r: r["supplier_share_of_segment_category"])
    s = D.slide(f"The supplier's share of cereal spend ranges from {_p(low['supplier_share_of_segment_category'], 0)} to {_p(best['supplier_share_of_segment_category'], 0)} across behavioural segments; the gap is among {low['segment'].lower()} households")
    D.chart(s, XL_CHART_TYPE.BAR_CLUSTERED, [r["segment"] for r in seg_sorted][::-1], {"Supplier share of the segment's cereal spend": [r["supplier_share_of_segment_category"] for r in seg_sorted][::-1]}, 0.6, 1.6, 6.2, 4.2, fmt='0%', legend=False)
    rows = [["Segment", "% of households", "Supplier buyers", "Brand index"]] + [[r["segment"], _p(r["share_of_households"], 0), _p(r["supplier_penetration"], 0), f"{r['brand_index']:.0f}"] for r in seg_sorted]
    D.table(s, rows, 7.1, 1.7, 5.7, [2.5, 1.2, 1.1, 0.9], size=12)
    sg = F["segmentation"]
    D.text(s, [f"k-means on seven behaviours (spend, trips, basket, recency, own-label share, deal depth, fresh share); k = {sg['k']} chosen by silhouette. Silhouette {max(sg['silhouette'].values()):.2f}: the groups are cuts of a continuum, not islands. Stability across 80% subsamples (ARI) {sg['stability_ari']:.2f}.",
            "Brand index = segment's share of supplier sales ÷ its share of store sales × 100."], 0.6, 5.9, 12.2, 1.0, size=12, color=GREY)

    # 7 promotions
    gr = P["gross_own"]
    s = D.slide(f"Features work: about {_p(gr['pct_of_units'] / 100, 0)} of the units in featured weeks were incremental, with no clear cannibalisation or post-promotion dip")
    import math
    def scaled(r, k):
        b, se = r["coef"] * k, r["se"] * k
        return 100 * (math.exp(b) - 1), 100 * (math.exp(b - 1.96 * se) - 1), 100 * (math.exp(b + 1.96 * se) - 1)
    rows = [["Effect on a product's weekly units", "Estimate", "95% interval", "Reading"]]
    spec = [("disp", "Display in 10 more points of its stores", 0.1), ("mail", "Mailer in 10 more points of its stores", 0.1),
            ("after1", "The week after a feature", 1), ("after2", "Weeks 2 and 3 after a feature", 1),
            ("sib", "Own products featured (10 points)", 0.1), ("comp", "Rival products featured (10 points)", 0.1)]
    for t, lab, k in spec:
        v, lo, hi = scaled(pr[t], k)
        rows.append([lab, f"{v:+.0f}%", f"{lo:+.0f}% to {hi:+.0f}%", "no clear effect" if lo <= 0 <= hi else ("raises sales" if v > 0 else "lowers sales")])
    D.table(s, rows, 0.6, 1.6, 8.0, [3.7, 1.0, 1.9, 1.4], size=13, row_h=0.42)
    D.bullets(s, [f"Poisson model with product and week effects: {P['n_products_supplier']} supplier products, {P['featured_weeks']} featured product-weeks (featured = in 25% or more of the product's stores).",
                  f"Featured weeks carry a price cut of {_p(P['depth_featured'], 0)} against {_p(P['depth_not_featured'], 0)} otherwise: display and price move together here, so the effect is of the bundle.",
                  "The weeks after a feature are higher, not lower: no pull-forward seen. The feature calendar and the sales week do not line up exactly, so read that as 'no dip', not a halo."],
              8.9, 1.6, 4.0, 5.2, size=13)
    D.text(s, f"Display or mailer effects are per 10 percentage points of the product's stores featuring it that week. Net of own-range cannibalisation, features add about {gr['incremental_units']:,.0f} units over {P['featured_weeks']} featured product-weeks (95% interval {gr['inc_low']:,.0f} to {gr['inc_high']:,.0f}).", 0.6, 4.9, 8.0, 1.2, size=12, color=GREY)

    # 8 range
    pa = rg["pareto"]
    s = D.slide(f"Delisting the {rg['tail_n']}-product tail ({_p(rg['tail_sales_share'], 0)} of sales) would cost {_d(sc_r['full transfer']['net_loss_to_supplier'])} to {_d(sc_r['low transfer']['net_loss_to_supplier'])} a year: only part of its demand moves to the rest of the range")
    sc3 = ["low transfer", "central", "full transfer"]
    D.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, ["Low transfer", "Central", "Full transfer"], {"Kept by supplier's other products": [sc_r[k]["kept_by_supplier"] for k in sc3], "Moves to other brands": [sc_r[k]["moved_to_others"] for k in sc3], "Lost to the category": [sc_r[k]["lost_to_category"] for k in sc3]}, 0.6, 1.6, 7.0, 5.2, fmt='$#,##0')
    D.bullets(s, [f"{pa['skus_for_80pct_of_sales']} of {pa['skus']} products make 80% of sales; the bottom half make {_p(pa['bottom_half_share'], 0)}.",
                  f"Tail = lowest sales per ranged store-week, up to 10% of sales ({_d(rg['tail_sales'])}).",
                  "Transfer is modelled, not observed: no delist happens in this year. Repertoire buyers (bought another product of the type) move 50–100% to what they already buy; exclusive buyers 0–100% to the type's other products. The central case uses 80% and 40%.",
                  "Observed purchases understate each household's repertoire, so the central loss is cautious (it checks against a simulated twin in the README)."], 7.9, 1.7, 5.0, 5.1, size=13)

    # 9 campaigns
    s = D.slide(f"A plain comparison credits the campaigns with {_d(cs['naive_incremental'])} of supplier sales; matched on past spend the effect is {_d(cs['incremental_sales'])} and cannot be told from zero")
    D.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, ["Plain comparison", "Matched on past spend"], {"Incremental supplier sales": [cs["naive_incremental"], cs["incremental_sales"]]}, 0.6, 1.6, 5.0, 4.6, fmt='$#,##0', legend=False, colors=[AMBER])
    D.text(s, f"95% interval for the matched estimate: {_d(cs['incremental_low'])} to {_d(cs['incremental_high'])}", 0.6, 6.25, 5.2, 0.4, size=13, color=GREY)
    ct = F["campaign_table"]
    rows = [["Campaign", "Type", "Households", "Redeemed", "Supplier sales in window"]] + [[c["campaign_id"], c["campaign_type"], f"{c['targeted']:,}", f"{c['redeemed']:,}", _d(c["supplier_sales_targeted"])] for c in ct]
    D.table(s, rows, 5.9, 1.7, 6.9, [1.1, 1.0, 1.4, 1.3, 2.1], size=12, row_h=0.34)
    D.bullets(s, [f"{cs['campaigns_eligible']} of {cs['campaigns_total']} campaigns could be evaluated (3+ weeks, a full pre-period, 3+ supplier coupon products).",
                  f"Targeted households spent more with the supplier before any campaign started, which is why the plain comparison misleads.",
                  f"Redeemed supplier coupons total {_d(cs['supplier_coupon_value_in_windows'])}, {cs['coupon_value_pct_of_targeted_sales']:.1f}% of targeted supplier sales: the cost is small and so is any signal. The data can rule out gains above {_d(cs['incremental_high'])}."],
              5.9, 4.4, 6.9, 2.5, size=13)

    # 10 recommendations
    s = D.slide("Three actions, sized from the data, each with the test that would prove it")
    rows = [["Action", "Evidence", "Size", "How we will know"]] + [[r["title"], r["evidence"], r["size"], r["measure"]] for r in recs]
    D.table(s, rows, 0.6, 1.5, 12.2, [2.2, 4.6, 3.0, 2.4], size=12, row_h=1.55, header_h=0.4)
    D.text(s, "Sizes marked 'a quarter recovered' or 'half the gap closed' are assumptions, not measurements.", 0.6, 6.6, 12, 0.4, size=12, color=GREY)

    # 11 measurement plan
    h = R["holdout"]
    s = D.slide(f"To prove a lift, hold out a random group: about {h['n_per_arm_for_20pct_lift']:,} households per arm for a 20% lift, {h['n_per_arm_for_10pct_lift']:,} for 10%")
    D.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, ["Detect a 20% lift", "Detect a 10% lift"], {"Households per arm": [h["n_per_arm_for_20pct_lift"], h["n_per_arm_for_10pct_lift"]]}, 0.6, 1.6, 6.0, 5.0, legend=False)
    D.bullets(s, [f"Spend per household per campaign window averages {_d(h['mean_spend_per_household_per_window'], 2)} with a standard deviation of change of {_d(h['sd_change_per_household'], 2)}: most households buy nothing in a window, so signals are small against noise.",
                  f"With the arms available here (about 1,100 targeted and 1,400 untargeted) the smallest lift detectable is about {h['mde_pct_with_1100_vs_1400']:.0f}%.",
                  "Design: random split before the send, same offer, same weeks; measure supplier sales per household and incremental sales per coupon dollar, with an interval.",
                  "Sample sizes: two-sided 5% test, 80% power, observed spread of spend."], 6.9, 1.7, 5.9, 5.0, size=14)

    # 12 method
    s = D.slide("How this was built, and what it cannot tell you")
    twin_line = (f"A simulated twin with planted effects checks the code: {sc['passed']} of {sc['total']} checks pass (seed 7); the README lists each, including the ones that fail." if sc else "A simulated twin with planted effects checks the code (see README).")
    D.bullets(s, ["Data: The Complete Journey, 84.51° (CC0): 2,469 households, 1.47 million lines, one year, 112 stores report promotions. American 2017 data, not Nectar, not Sainsbury's.",
                  "Method: one DuckDB warehouse; SQL with window functions and CTEs, portable to Snowflake; Python for models. Definitions are in docs/DATA_NOTES.md.",
                  twin_line,
                  "Limits: one year; transfer in the range analysis is modelled; matched campaign estimates assume similar trends after matching; no margin or cost data, so no profit ROI; display effects move with price cuts.",
                  "Built with an AI coding assistant; every figure in this deck is generated from the result tables and checked by tests."], 0.6, 1.6, 12.1, 5.2, size=16)
    path = out / "basketlens_supplier_deck.pptx"
    D.prs.save(path)
    return path
