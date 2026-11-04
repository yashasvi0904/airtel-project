"""Deterministic business logic: validators, eligibility, pricing, recommender."""
import pytest

from app.services import datasets
from app.services.eligibility import check_eligibility, dependency_status, validate_selection
from app.services.kyc.validators import (gstin_checksum_char, is_valid_gstin, is_valid_udyam, normalise_udyam, repair_gstin)
from app.services.pricing import build_quote, term_options, unit_price
from app.services.profile import build_profile, infer_segment
from app.services.recommender import build_bundles, default_quantity


def prof(**kw):
    base = dict(business_name="Test Co", business_type="Kirana store", city="Pune", employees=3, sites=1, current_internet="Mobile hotspot")
    base.update(kw)
    return build_profile(base)


# ------------------------------------------------------------------ validators

def test_every_registry_gstin_is_structurally_valid():
    """The dataset README promises real structure + checksum for all registry GSTINs (4th PAN char is 'X')."""
    bad = [g for g in datasets.gstin_registry()["gstin"] if not is_valid_gstin(g)]
    assert bad == []


def test_gstin_checksum_detects_tampered_digit():
    assert is_valid_gstin("08YKZXS5189L1ZO")
    assert not is_valid_gstin("08YKZXS8189L1ZO")  # K06: one digit altered
    assert gstin_checksum_char("08YKZXS5189L1Z") == "O"


@pytest.mark.parametrize("raw,expected", [
    ("37LDYXK0296F1ZB", "37LDYXK0296F1ZB"),
    ("37LDYXK0296FIZB", "37LDYXK0296F1ZB"),   # I read instead of 1
    ("O7CPCXN0398P1ZT", "07CPCXN0398P1ZT"),   # letter O instead of 0
    ("37 LDYXK0296F1ZB", "37LDYXK0296F1ZB"),
])
def test_ocr_repair_recovers_registry_gstin(raw, expected):
    fixed, _ = repair_gstin(raw)
    assert fixed == expected


def test_udyam_format():
    assert is_valid_udyam("UDYAM-MH-00-9516696")
    assert is_valid_udyam("udyam mh 00 9516696".replace(" ", "-"))
    assert not is_valid_udyam("UDYAM-MH-9516696")
    assert normalise_udyam("UDYAMMH009516696") == "UDYAM-MH-00-9516696"


# ------------------------------------------------------------------ profile / segment

def test_segment_inference_uses_business_type_and_sites():
    assert infer_segment("Kirana store", 3, 1) == "Micro retail & services"
    assert infer_segment("Dental clinic", 14, 1) == "Professional offices"
    assert infer_segment("Textile unit", 85, 1) == "Small manufacturers"
    assert infer_segment("Salon", 10, 4) == "Small multi-site businesses"


def test_city_tier_comes_from_dataset():
    assert prof(city="Pune").city_tier == 1
    assert prof(city="Nagpur").city_tier == 2


# ------------------------------------------------------------------ eligibility

def test_p03_requires_tier1_5_employees_and_gstin(catalogue_map):
    p03 = catalogue_map["P03"]
    ok = check_eligibility(p03, prof(employees=10, gstin="29FGUXG3354T1ZQ", has_gstin=True))
    assert ok.status == "yes"
    tier2 = check_eligibility(p03, prof(city="Nagpur", employees=10, gstin="27XUIXG0767D1ZP", has_gstin=True))
    assert tier2.status == "no" and any(r["code"] == "city_tier" for r in tier2.reasons)
    small = check_eligibility(p03, prof(employees=2, gstin="29FGUXG3354T1ZQ", has_gstin=True))
    assert any(r["code"] == "min_employees" for r in small.reasons)
    no_gst = check_eligibility(p03, prof(employees=10))
    assert no_gst.status == "no" and "Add your GSTIN" in no_gst.unlock


def test_cancelled_gstin_blocks_gst_products(catalogue_map):
    cancelled = prof(employees=10, gstin="37IHKXV5167L1ZS", has_gstin=True)  # K01 - Cancelled in registry
    assert cancelled.gstin_status == "cancelled"
    el = check_eligibility(catalogue_map["P14"], cancelled)  # Business SMS requires GSTIN
    assert el.status == "no" and el.reasons[0]["code"] == "gstin_inactive"


def test_declared_but_unverified_gstin_is_conditional(catalogue_map):
    el = check_eligibility(catalogue_map["P15"], prof(has_gstin=True))
    assert el.status == "conditional"


def test_dependency_rules(catalogue_map):
    cctv = catalogue_map["P23"]
    assert not dependency_status(cctv, {"P07"})["satisfied"]
    assert dependency_status(cctv, {"P01", "P07"})["satisfied"]


def test_validate_selection_flags_every_problem(catalogue_map):
    p = prof(employees=2)
    errs = validate_selection([{"product_id": "P23", "quantity": 2}, {"product_id": "P10", "quantity": 1}, {"product_id": "P99", "quantity": 1}], 12, p, catalogue_map)
    codes = {e["code"] for e in errs}
    assert {"dependency", "ineligible", "unknown_product"} <= codes
    assert validate_selection([{"product_id": "P01", "quantity": 1}, {"product_id": "P23", "quantity": 2}], 12, p, catalogue_map) == []
    # term below a product's minimum contract
    assert any(e["code"] == "term" for e in validate_selection([{"product_id": "P01", "quantity": 1}], 6, p, catalogue_map))
    assert validate_selection([], 12, p, catalogue_map)[0]["code"] == "empty"


# ------------------------------------------------------------------ pricing

def test_unit_price_stays_inside_catalogue_range(catalogue_map):
    for p in catalogue_map.values():
        for term in (12, 24):
            for qty in (1, 5, 12):
                price, _, pos = unit_price(p, qty, term, 5)
                assert p.price_min <= price <= p.price_max and 0 <= pos <= 1


def test_longer_term_never_costs_more(catalogue_map):
    p = catalogue_map["P02"]
    prices = [unit_price(p, 1, t, 1)[0] for t in (6, 12, 24)]
    assert prices[0] >= prices[1] >= prices[2]
    assert prices[0] == p.price_max and prices[2] < prices[0]


def test_quote_totals_setup_and_gst(catalogue_map):
    items = [{"product_id": "P01", "quantity": 2}, {"product_id": "P19", "quantity": 1}, {"product_id": "P07", "quantity": 3}]
    q = build_quote(items, 12, catalogue_map)
    t = q["totals"]
    assert t["setup_subtotal"] == 2500  # only P19 has a setup fee (2500 x 1)
    assert t["monthly_subtotal"] == pytest.approx(sum(l["monthly"] for l in q["items"]))
    assert t["monthly_gst"] == pytest.approx(round(t["monthly_subtotal"] * 0.18, 2))
    assert t["monthly_total"] == pytest.approx(t["monthly_subtotal"] + t["monthly_gst"])
    assert t["first_payment"] == pytest.approx(t["monthly_total"] + t["setup_total"])
    assert t["contract_value"] == pytest.approx(t["monthly_total"] * 12 + t["setup_total"])
    assert q == build_quote(items, 12, catalogue_map)  # deterministic


def test_setup_fee_scales_with_quantity(catalogue_map):
    q = build_quote([{"product_id": "P01", "quantity": 1}, {"product_id": "P23", "quantity": 4}], 12, catalogue_map)
    assert q["totals"]["setup_subtotal"] == 4 * 1800


def test_historical_bundle_values_reconcile_with_catalogue(catalogue_map):
    """Cross-check against the leads data: activated bundles' setup fees equal sum(qty x catalogue setup)."""
    act = datasets.leads().query("activated").head(60)
    for _, r in act.iterrows():
        setup = sum(int(it.split("x")[1]) * catalogue_map[it.split("x")[0]].setup_fee for it in r.bundle_products.split(";"))
        assert setup == r.one_time_setup_inr


def test_term_options_respect_min_contract(catalogue_map):
    assert term_options([catalogue_map["P10"]]) == [24]
    assert term_options([catalogue_map["P01"], catalogue_map["P07"]]) == [12, 24]
    assert term_options([catalogue_map["P07"]]) == [1, 12, 24]


# ------------------------------------------------------------------ recommender

def all_deps_ok(rec, cat):
    for tier in rec["tiers"].values():
        ids = {i["product_id"] for i in tier["items"]}
        for i in tier["items"]:
            assert dependency_status(cat[i["product_id"]], ids)["satisfied"], (tier["name"], i["product_id"])


def test_micro_retailer_without_gstin_gets_no_gst_products(catalogue_map):
    p = prof(city="Nagpur", business_type="Pharmacy")
    rec = build_bundles(p, {"wants": ["whatsapp", "sms", "cctv", "pos"]}, catalogue_map)
    ids = {i["product_id"] for t in rec["tiers"].values() for i in t["items"]}
    assert "P15" not in ids and "P14" not in ids  # both require GSTIN
    assert {"P19", "P23"} <= ids
    assert {e["product_id"] for e in rec["excluded"]} >= {"P15", "P14"}
    all_deps_ok(rec, catalogue_map)


def test_every_item_in_every_tier_is_eligible(catalogue_map):
    cases = [
        prof(),
        prof(city="Nagpur", business_type="Textile unit", employees=85, has_gstin=True, gstin="27XUIXG0767D1ZP"),
        prof(business_type="Restaurant chain", employees=71, sites=8, has_gstin=True, gstin="29FGUXG3354T1ZQ"),
        prof(business_type="Dental clinic", employees=14, has_gstin=True, gstin="19EOGXH4115Y1ZL", city="Kolkata"),
    ]
    for p in cases:
        rec = build_bundles(p, {}, catalogue_map)
        all_deps_ok(rec, catalogue_map)
        for t in rec["tiers"].values():
            for i in t["items"]:
                assert check_eligibility(catalogue_map[i["product_id"]], p).ok, (p.business_type, i["product_id"])


def test_multi_site_gets_sdwan_only_with_gstin(catalogue_map):
    with_gst = prof(business_type="Restaurant chain", employees=71, sites=8, has_gstin=True, gstin="29FGUXG3354T1ZQ")
    without = prof(business_type="Restaurant chain", employees=71, sites=8)
    ids = lambda p: {i["product_id"] for i in build_bundles(p, {}, catalogue_map)["tiers"]["recommended"]["items"]}
    assert "P10" in ids(with_gst)
    assert "P10" not in ids(without)


def test_no_fibre_picks_wireless(catalogue_map):
    rec = build_bundles(prof(), {"fibre_available": False}, catalogue_map)
    ids = [i["product_id"] for i in rec["tiers"]["starter"]["items"]]
    assert "P04" in ids and "P01" not in ids


def test_budget_selects_smaller_tier_and_flags_over_budget(catalogue_map):
    p = prof(business_type="Dental clinic", employees=14, monthly_budget=1500)
    rec = build_bundles(p, {"wants": ["email", "security", "backup"]}, catalogue_map)
    assert rec["over_budget"] and rec["recommended_tier"] == "starter"
    rich = prof(business_type="Dental clinic", employees=14, monthly_budget=500000)
    assert not build_bundles(rich, {}, catalogue_map)["over_budget"]


def test_default_quantities_follow_units(catalogue_map):
    p = prof(business_type="Restaurant chain", employees=40, sites=5)
    assert default_quantity(catalogue_map["P02"], p, {}) == 5      # per site
    assert default_quantity(catalogue_map["P16"], p, {}) == 40     # per user
    assert default_quantity(catalogue_map["P23"], p, {"cameras": 6}) == 6
