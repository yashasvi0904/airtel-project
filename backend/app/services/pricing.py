"""Deterministic quote engine. All amounts are Decimal rupees; prices come from the catalogue + pricing_rules.json."""
import json
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from ..config import get_settings
from ..models import Product

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "pricing_rules.json"


@lru_cache
def rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def D(x) -> Decimal:
    return Decimal(str(x))


def money(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _best(table: list[dict], key: str, value: int) -> dict | None:
    for row in table:  # tables are ordered from the highest threshold down
        if value >= row[key]:
            return row
    return None


def required_term(products: list[Product]) -> int:
    return max((p.min_contract_months for p in products), default=1)


def term_options(products: list[Product]) -> list[int]:
    req = required_term(products)
    return sorted({req} | {t for t in rules()["term_options"] if t >= req})


def unit_price(product: Product, quantity: int, term_months: int, distinct_products: int) -> tuple[Decimal, list[dict], float]:
    """Pick a price inside [price_min, price_max] using term, volume and bundle-size policy."""
    r = rules()
    contributions = []
    for table, key, value in (
        (r["term_position"], "min_months", term_months),
        (r["volume_position"], "min_qty", quantity),
        (r["bundle_position"], "min_products", distinct_products),
    ):
        row = _best(table, key, value)
        if row:
            contributions.append({"label": row["label"], "position": row["position"]})
    position = min(D(1), sum((D(c["position"]) for c in contributions), D(0)))
    lo, hi = D(product.price_min), D(product.price_max)
    price = (hi - position * (hi - lo)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return price, contributions, float(position)


def build_quote(items: list[dict], term_months: int, catalogue: dict[str, Product], monthly_spend: float | None = None) -> dict:
    """items: [{product_id, quantity}]. Caller must validate eligibility/dependencies first."""
    settings = get_settings()
    gst = D(settings.gst_rate_percent) / D(100)
    products = [catalogue[i["product_id"]] for i in items]
    distinct = len(products)

    lines, monthly_sub, setup_sub, list_monthly = [], D(0), D(0), D(0)
    for it, p in zip(items, products):
        qty = int(it["quantity"])
        price, discounts, position = unit_price(p, qty, term_months, distinct)
        monthly = price * qty
        setup = D(p.setup_fee) * qty
        monthly_sub += monthly
        setup_sub += setup
        list_monthly += D(p.price_max) * qty
        lines.append({
            "product_id": p.product_id,
            "name": p.product_name,
            "category": p.category,
            "unit": p.unit,
            "quantity": qty,
            "unit_price": money(price),
            "list_unit_price": p.price_max,
            "floor_unit_price": p.price_min,
            "discounts": discounts,
            "price_position": position,
            "monthly": money(monthly),
            "setup_unit": p.setup_fee,
            "setup": money(setup),
            "install_days": p.install_days,
            "min_contract_months": p.min_contract_months,
        })

    monthly_gst = monthly_sub * gst
    setup_gst = setup_sub * gst
    monthly_total = monthly_sub + monthly_gst
    setup_total = setup_sub + setup_gst
    totals = {
        "monthly_subtotal": money(monthly_sub),
        "monthly_gst": money(monthly_gst),
        "monthly_total": money(monthly_total),
        "setup_subtotal": money(setup_sub),
        "setup_gst": money(setup_gst),
        "setup_total": money(setup_total),
        "first_payment": money(monthly_total + setup_total),
        "term_months": term_months,
        "contract_value": money(monthly_total * term_months + setup_total),
        "list_monthly_subtotal": money(list_monthly),
        "discount_vs_list": money(list_monthly - monthly_sub),
        "gst_rate_percent": settings.gst_rate_percent,
        "gst_note": "GST is not specified in the supplied catalogue; shown at the configured indicative rate.",
        "install_days": max((p.install_days for p in products), default=0),
        "term_options": term_options(products),
        "required_term_months": required_term(products),
    }
    if monthly_spend:
        totals["current_monthly_spend"] = monthly_spend
        totals["vs_current_spend"] = money(monthly_sub - D(monthly_spend))
    return {"items": lines, "totals": totals}
