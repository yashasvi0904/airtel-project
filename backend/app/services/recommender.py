"""Deterministic recommendation engine.

Inputs: business profile + structured needs (from the advisor or onboarding) + catalogue + historical attach rates.
Output: tiered bundles with per-product reasons. The LLM only phrases these reasons; it cannot add products.
"""
import math

from ..models import Product
from . import datasets
from .eligibility import check_eligibility, dependency_status
from .pricing import build_quote, term_options
from .profile import SEGMENT_CODE, BusinessProfile

CONNECTIVITY_MAIN = ["P01", "P02", "P03", "P04", "P05", "P06"]

# need tag -> product (domain mapping of customer language to catalogue ids)
NEED_PRODUCTS = {
    "whatsapp": "P15", "sms": "P14", "email": "P16", "backup": "P17", "security": "P20",
    "firewall": "P21", "cctv": "P23", "pos": "P19", "website": "P18", "phone_system": "P12",
    "toll_free": "P13", "iot": "P24", "fleet": "P25", "failover": "P09", "sd_wan": "P10",
    "static_ip": "P11", "guest_wifi": "P22",
}
NEED_LABEL = {
    "whatsapp": "a WhatsApp channel for customers", "sms": "SMS alerts/promotions", "email": "business email",
    "backup": "cloud backup", "security": "protection for your PCs and phones", "firewall": "a managed firewall",
    "cctv": "CCTV", "pos": "billing / POS", "website": "a website", "phone_system": "a business phone system",
    "toll_free": "a toll-free number", "iot": "machine monitoring", "fleet": "vehicle tracking",
    "failover": "a backup link when the main internet fails", "sd_wan": "central management across sites",
    "static_ip": "a static IP", "guest_wifi": "guest Wi-Fi",
}
SOCIAL_PROOF_MIN = 0.25  # share of activated customers in the segment who bought the product
SEGMENT_ESSENTIAL = 0.8
SEGMENT_POPULAR = 0.4


def default_quantity(p: Product, profile: BusinessProfile, needs: dict) -> int:
    u = p.unit
    sites, emp = max(1, profile.sites), max(1, profile.employees)
    if u == "per site":
        return sites
    if u == "per line":
        if needs.get("mobile_lines"):
            return int(needs["mobile_lines"])
        return max(1, min(math.ceil(emp / 2), 6)) if p.product_id == "P07" else max(1, min(sites, 6))
    if u == "per user":
        return emp
    if u == "per device":
        if p.product_id == "P24":
            return int(needs.get("machines") or min(5, emp))
        return min(emp, 50)
    if u == "per camera":
        return int(needs.get("cameras") or min(4 * sites, 24))
    if u == "per counter":
        return int(needs.get("pos_counters") or min(sites, 12))
    if u == "per vehicle":
        return int(needs.get("vehicles") or 3)
    if u == "per channel":
        return max(3, min(emp // 4, 12))
    return 1  # per IP / number / pack / account


def pick_connectivity(profile: BusinessProfile, needs: dict, catalogue: dict[str, Product]) -> tuple[str | None, list[str]]:
    eps = math.ceil(profile.employees / max(1, profile.sites))
    seg = SEGMENT_CODE.get(profile.segment, "micro")
    reasons: list[str] = []
    if needs.get("mobile_only"):
        return None, ["You asked for mobile connectivity only, so no broadband is included."]
    if needs.get("fibre_available") is False:
        order = ["P04"]
        reasons.append("Fibre is not available at your site, so a plug-and-play 5G wireless link is used instead.")
    elif seg == "mfg":
        order = ["P06", "P05", "P03", "P02"] if profile.employees >= 80 else (["P05", "P03", "P02"] if profile.employees >= 10 else ["P02", "P01"])
    elif seg in ("prof", "multi"):
        order = ["P03", "P02"] if eps > 30 else (["P02", "P01"] if eps > 8 else ["P01", "P02"])
    else:
        order = ["P01", "P04"]
    if needs.get("priority") == "price" and eps <= 15 and "P04" not in order[:1]:
        order = ["P01"] + [o for o in order if o != "P01"]
    for pid in order + ["P01", "P04"]:
        p = catalogue.get(pid)
        if p and check_eligibility(p, profile).ok:
            if not reasons:
                reasons.append(_connectivity_reason(pid, profile, eps))
            return pid, reasons
    return None, ["No broadband product is available for this location and size."]


def _connectivity_reason(pid: str, profile: BusinessProfile, eps: int) -> str:
    cur = profile.current_internet
    base = {
        "P01": f"100 Mbps unlimited fibre comfortably serves about {eps} people per site.",
        "P02": f"300 Mbps fibre suits roughly {eps} people per site with cloud apps and video calls.",
        "P03": f"With about {eps} people per site, a 1 Gbps line with priority support avoids slowdowns.",
        "P04": "A plug-and-play 5G link goes live in about two days without any cabling.",
        "P05": "A dedicated 1:1 leased line gives the guaranteed bandwidth a production unit depends on.",
        "P06": "A 100 Mbps dedicated line with a 99.9% SLA suits a larger unit with many users and machines.",
    }[pid]
    if cur == "Mobile hotspot":
        base += " This replaces your mobile hotspot, which is the weakest setup for UPI/POS and cloud work."
    elif cur == "Home broadband":
        base += " This replaces home broadband with a business-grade connection and business support."
    return base


def _ensure_dependencies(items: dict[str, dict], profile: BusinessProfile, catalogue: dict[str, Product], core: str | None) -> list[str]:
    """Add or drop products so every requires_one_of is satisfied. Returns notes."""
    notes: list[str] = []
    for _ in range(3):
        changed = False
        for pid in list(items):
            p = catalogue[pid]
            dep = dependency_status(p, set(items))
            if dep["satisfied"]:
                continue
            fix = core if core in p.requires_one_of else None
            if not fix:
                fix = next((d for d in p.requires_one_of if d in catalogue and check_eligibility(catalogue[d], profile).ok), None)
            if fix and fix not in items:
                items[fix] = {"product_id": fix, "quantity": default_quantity(catalogue[fix], profile, {}), "role": "dependency",
                              "reasons": [f"{p.product_name} needs one of {', '.join(p.requires_one_of)}; this is the best fit for you."]}
                notes.append(f"Added {catalogue[fix].product_name} because {p.product_name} requires it.")
                changed = True
            elif not fix:
                del items[pid]
                notes.append(f"Removed {p.product_name}: no eligible prerequisite product is available.")
                changed = True
        if not changed:
            break
    return notes


def build_bundles(profile: BusinessProfile, needs: dict, catalogue: dict[str, Product], term_months: int | None = None) -> dict:
    needs = needs or {}
    seg = profile.segment
    rates = datasets.segment_attach_rates().get(seg, {})
    seg_label = seg.lower()
    seg_code = SEGMENT_CODE.get(seg, "micro")
    excluded: list[dict] = []

    def add(bucket: dict, pid: str, role: str, reason: str, qty: int | None = None):
        p = catalogue.get(pid)
        if p is None:
            return
        el = check_eligibility(p, profile)
        if not el.ok:
            if not any(e["product_id"] == pid for e in excluded):
                excluded.append({"product_id": pid, "name": p.product_name, "eligibility": el.as_dict()})
            return
        if pid in bucket:
            if reason not in bucket[pid]["reasons"]:
                bucket[pid]["reasons"].append(reason)
            return
        bucket[pid] = {"product_id": pid, "quantity": qty or default_quantity(p, profile, needs), "role": role, "reasons": [reason]}

    core: dict[str, dict] = {}
    conn, conn_reasons = pick_connectivity(profile, needs, catalogue)
    if conn:
        add(core, conn, "core", conn_reasons[0])
    elif conn_reasons and needs.get("mobile_only") is not True:
        excluded.append({"product_id": "-", "name": "Broadband", "eligibility": {"status": "no", "reasons": [{"code": "none", "message": conn_reasons[0]}], "unlock": []}})
    mobile = "P08" if seg_code in ("multi", "mfg") else "P07"
    if needs.get("wants_mobile", True):
        add(core, mobile, "core", "Business SIMs give you priority care and one bill with your internet." if mobile == "P08"
            else "Business mobile lines keep the owner and staff reachable on one business plan.")

    # explicit needs: things the customer asked for by name. These survive into every tier, including Starter.
    asked_items: dict[str, dict] = {}
    for tag in needs.get("wants", []):
        pid = NEED_PRODUCTS.get(tag)
        if pid:
            add(asked_items, pid, "need", f"You asked for {NEED_LABEL.get(tag, tag)}.")
    # inferred needs: derived from pain points / site count
    need_items: dict[str, dict] = {}
    if needs.get("pain_downtime") or needs.get("priority") == "reliability":
        if profile.sites >= 1:
            add(need_items, "P09", "need", "You told us downtime hurts; automatic 4G/5G failover keeps you online when the main link drops.")

    # data-driven segment essentials / popular add-ons (excluding connectivity, which is rule-driven)
    essentials, popular, extras = {}, {}, {}
    for pid, rate in sorted(rates.items(), key=lambda kv: -kv[1]):
        if pid in CONNECTIVITY_MAIN or pid in ("P07", "P08") or pid not in catalogue:
            continue
        pct = round(rate * 100)
        why = f"{pct}% of activated {seg_label} customers bought this."
        if rate >= SEGMENT_ESSENTIAL:
            add(essentials, pid, "segment_essential", why)
        elif rate >= SEGMENT_POPULAR:
            add(popular, pid, "segment_popular", why)
        elif rate >= SOCIAL_PROOF_MIN:
            add(extras, pid, "segment_extra", why)

    # multi-site: central management
    if profile.sites >= 3:
        add(need_items, "P10", "need", f"With {profile.sites} sites, central SD-WAN management gives one control point and one bill.")
        add(need_items, "P09", "need", "Each site stays online through automatic failover.")

    def merge(*buckets: dict) -> dict:
        out: dict[str, dict] = {}
        for b in buckets:
            for pid, it in b.items():
                if pid in out:
                    out[pid]["reasons"].extend(r for r in it["reasons"] if r not in out[pid]["reasons"])
                else:
                    out[pid] = {**it, "reasons": list(it["reasons"])}
        return out

    tiers_raw = {
        "starter": merge(core, asked_items),
        "recommended": merge(core, asked_items, need_items, essentials, popular),
        "complete": merge(core, asked_items, need_items, essentials, popular, extras),
    }
    notes: list[str] = []
    tiers = {}
    for name, items in tiers_raw.items():
        items = {k: v for k, v in items.items()}
        notes += _ensure_dependencies(items, profile, catalogue, conn)
        tiers[name] = list(items.values())

    # term and quotes
    ids = [catalogue[i["product_id"]] for i in tiers["complete"]]
    result = {"tiers": {}, "excluded": excluded, "notes": list(dict.fromkeys(notes)), "segment": seg, "attach_rates": rates}
    for name, items in tiers.items():
        prods = [catalogue[i["product_id"]] for i in items]
        opts = term_options(prods) if prods else [12]
        term = term_months if term_months in opts else (12 if 12 in opts else opts[0])
        quote = build_quote([{"product_id": i["product_id"], "quantity": i["quantity"]} for i in items], term, catalogue, profile.monthly_telecom_spend) if items else None
        result["tiers"][name] = {"name": name, "items": items, "term_months": term, "quote": quote}
    del ids

    # choose the default tier by budget
    budget = profile.monthly_budget
    chosen = "recommended"
    over_budget = False
    if budget:
        order = ["complete", "recommended", "starter"]
        fit = [t for t in order if result["tiers"][t]["quote"] and result["tiers"][t]["quote"]["totals"]["monthly_total"] <= budget]
        if fit:
            chosen = fit[0] if fit[0] != "complete" else "recommended"
            if result["tiers"]["recommended"]["quote"]["totals"]["monthly_total"] > budget and "recommended" not in fit:
                chosen = fit[0]
        else:
            chosen, over_budget = "starter", True
    result["recommended_tier"] = chosen
    result["over_budget"] = over_budget
    result["budget"] = budget
    return result


def explorer(profile: BusinessProfile, catalogue: dict[str, Product]) -> list[dict]:
    """Every catalogue product with eligibility, for the 'browse everything' view."""
    from .catalogue import product_dict

    rates = datasets.segment_attach_rates().get(profile.segment, {})
    out = []
    for p in catalogue.values():
        el = check_eligibility(p, profile)
        out.append({**product_dict(p), "eligibility": el.as_dict(), "default_quantity": default_quantity(p, profile, {}),
                    "segment_attach_rate": rates.get(p.product_id, 0.0)})
    return out


def suggest_fixes(errors: list[dict], items: list[dict], profile: BusinessProfile, catalogue: dict[str, Product]) -> list[dict]:
    """For dependency errors, offer the concrete options: add a prerequisite or remove the dependent product."""
    fixes = []
    for e in errors:
        if e["code"] != "dependency":
            continue
        opts = [d for d in e.get("required", []) if d in catalogue and check_eligibility(catalogue[d], profile).ok]
        fixes.append({
            "product_id": e["product_id"],
            "add_one_of": [{"product_id": d, "name": catalogue[d].product_name} for d in opts],
            "or_remove": e["product_id"],
        })
    return fixes
