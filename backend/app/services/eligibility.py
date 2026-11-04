"""Deterministic product eligibility and dependency rules. The LLM never decides any of this."""
from dataclasses import dataclass, field

from ..models import Product
from .profile import BusinessProfile


@dataclass
class Eligibility:
    status: str  # yes | conditional | no
    reasons: list[dict] = field(default_factory=list)  # {code, message}
    unlock: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("yes", "conditional")

    def as_dict(self) -> dict:
        return {"status": self.status, "reasons": self.reasons, "unlock": self.unlock}


def _r(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def check_eligibility(product: Product, profile: BusinessProfile) -> Eligibility:
    reasons: list[dict] = []
    unlock: list[str] = []
    conditional = False

    if profile.city_tier not in product.city_tiers:
        tiers = " and ".join(str(t) for t in product.city_tiers)
        reasons.append(_r("city_tier", f"Sold only in tier {tiers} cities; {profile.city or 'your city'} is tier {profile.city_tier}."))
    if profile.employees < product.min_employees:
        reasons.append(_r("min_employees", f"Needs at least {product.min_employees} employees (you have {profile.employees})."))
    if profile.sites < product.min_sites:
        reasons.append(_r("min_sites", f"Needs at least {product.min_sites} sites (you have {profile.sites})."))
    if product.requires_gstin:
        st = profile.gstin_status
        if st == "active":
            pass
        elif st == "declared":
            conditional = True
            reasons.append(_r("gstin_pending", "Needs an active GSTIN - we will verify it during KYC."))
        elif st in ("cancelled", "suspended"):
            reasons.append(_r("gstin_inactive", f"Your GSTIN is {st} in the registry; an active GSTIN is required."))
            unlock.append("Reinstate your GST registration, then reapply")
        elif st in ("invalid", "not_found"):
            reasons.append(_r("gstin_invalid", "The GSTIN provided could not be validated; a valid active GSTIN is required."))
            unlock.append("Re-check the GSTIN you entered")
        else:
            reasons.append(_r("gstin_required", "Requires a valid, active GSTIN."))
            unlock.append("Add your GSTIN")

    hard = [x for x in reasons if x["code"] != "gstin_pending"]
    if hard:
        return Eligibility("no", reasons, unlock)
    return Eligibility("conditional" if conditional else "yes", reasons, unlock)


def dependency_status(product: Product, selected_ids: set[str]) -> dict:
    """requires_one_of: product needs at least one of the listed products in the same bundle."""
    if not product.requires_one_of:
        return {"required": [], "satisfied": True, "satisfied_by": []}
    hit = [p for p in product.requires_one_of if p in selected_ids]
    return {"required": product.requires_one_of, "satisfied": bool(hit), "satisfied_by": hit}


def validate_selection(
    items: list[dict], term_months: int, profile: BusinessProfile, catalogue: dict[str, Product]
) -> list[dict]:
    """Return a list of blocking errors for a selection (empty list = valid)."""
    errors: list[dict] = []
    if not items:
        return [_r("empty", "Select at least one product.")]
    ids = {i["product_id"] for i in items}
    seen: set[str] = set()
    for it in items:
        pid = it["product_id"]
        p = catalogue.get(pid)
        if p is None:
            errors.append({**_r("unknown_product", f"Unknown product {pid}."), "product_id": pid})
            continue
        if pid in seen:
            errors.append({**_r("duplicate", f"{p.product_name} appears more than once."), "product_id": pid})
        seen.add(pid)
        qty = it.get("quantity", 0)
        if not isinstance(qty, int) or qty < 1 or qty > 1000:
            errors.append({**_r("quantity", f"Invalid quantity for {p.product_name}."), "product_id": pid})
        el = check_eligibility(p, profile)
        if not el.ok:
            errors.append({**_r("ineligible", f"{p.product_name}: " + " ".join(x["message"] for x in el.reasons)), "product_id": pid})
        dep = dependency_status(p, ids)
        if not dep["satisfied"]:
            names = ", ".join(catalogue[d].product_name for d in dep["required"] if d in catalogue)
            errors.append({**_r("dependency", f"{p.product_name} needs one of: {names}."), "product_id": pid, "required": dep["required"]})
        if term_months < p.min_contract_months:
            errors.append({**_r("term", f"{p.product_name} has a minimum contract of {p.min_contract_months} months."), "product_id": pid})
    return errors
