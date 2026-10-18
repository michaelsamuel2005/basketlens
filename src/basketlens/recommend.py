"""Three recommendations, each with its evidence and size, written from the computed results (no hand-typed figures)."""
from __future__ import annotations


def _d(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def recommendations(res: dict) -> list[dict]:
    seg = res["segments"]["segments"]
    j = res["journeys"]
    tot_sup = float(seg.supplier_sales.sum())
    recs = []
    # 1. close the share gap in the segment where the supplier under-indexes on category spend
    best_share = seg.supplier_share_of_segment_category.max()
    seg = seg.assign(gap=best_share - seg.supplier_share_of_segment_category,
                     cat_sales=seg.supplier_sales / seg.supplier_share_of_segment_category)
    seg = seg.assign(prize=0.5 * seg.gap * seg.cat_sales)
    r1 = seg.sort_values("prize", ascending=False).iloc[0]
    recs.append({
        "title": f"Win share among {r1.segment.lower()} households",
        "evidence": (f"They are {100*r1.share_of_households:.0f}% of households and {100*r1.share_of_category_sales:.0f}% of "
                     f"category sales, but the supplier takes {100*r1.supplier_share_of_segment_category:.0f}% of their category "
                     f"spend against {100*best_share:.0f}% in the best segment (brand index {r1.brand_index:.0f})."),
        "action": "Target the segment with the products and offers its leaning points to; read the result against a random holdout.",
        "size": f"Closing half the gap is worth about {_d(r1.prize)} a year, {100*r1.prize/tot_sup:.0f}% of the supplier's category sales.",
        "measure": "Share of category spend in the segment, treated vs holdout households, over 12 weeks.",
        "value": float(r1.prize), "assumption": "Half the gap closed: an assumption, not a measurement."})
    # 2. win back lapsed buyers
    f, lc = j["flows"], j["lifecycle"]
    value = f["annualised_value_of_lapsed"]
    recs.append({
        "title": "Win back lapsed buyers before they settle elsewhere",
        "evidence": (f"{100*lc['lapse_rate']:.0f}% of established buyers ({lc['lapsed_to_others']} of {lc['established']}) stopped buying "
                     f"the supplier by the last quarter yet still buy the category; "
                     f"{100*f['pl_share_of_rest_q4']:.0f}% of what they spent on others was private label, against "
                     f"{100*f['pl_share_of_rest_all_households_q4']:.0f}% for all households, so the loss is to other brands."),
        "action": "Trigger an offer when an established buyer misses their usual gap; do not frame it as a private-label fight.",
        "size": f"These households spent about {_d(value)} a year with the supplier before lapsing; recovering a quarter is {_d(value/4)}.",
        "measure": "Return rate within 12 weeks, offered vs random holdout.",
        "value": float(value / 4), "assumption": "A quarter recovered: an assumption, not a measurement."})
    # 3. evaluate campaigns properly
    c, h = res["campaigns"]["summary"], res["holdout"]
    recs.append({
        "title": "Run the next campaign with a random holdout",
        "evidence": (f"A plain comparison credits the {c['campaigns_eligible']} evaluable campaigns with {_d(c['naive_incremental'])} of supplier "
                     f"sales; after matching on past spend the estimate is {_d(c['incremental_sales'])} "
                     f"(95% interval {_d(c['incremental_low'])} to {_d(c['incremental_high'])}). Targeted households already spent "
                     f"far more before the campaigns started."),
        "action": (f"Hold out a random group: about {h['n_per_arm_for_10pct_lift']:,} households per arm detects a 10% lift in supplier spend "
                   f"({h['n_per_arm_for_20pct_lift']:,} for 20%)."),
        "size": "Turns campaign spend from a guess into a measured return.",
        "measure": "Incremental supplier sales per coupon dollar, with an interval.",
        "value": None, "assumption": "Sample sizes assume the spread of spend seen in this data."})
    return recs
