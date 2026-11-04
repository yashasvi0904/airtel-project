"""Business profile helpers: segment inference, city tier, GSTIN standing."""
from dataclasses import dataclass, field

from . import datasets

SEGMENTS = [
    "Micro retail & services",
    "Professional offices",
    "Small multi-site businesses",
    "Small manufacturers",
]
SEGMENT_CODE = {
    "Micro retail & services": "micro",
    "Professional offices": "prof",
    "Small multi-site businesses": "multi",
    "Small manufacturers": "mfg",
}
CODE_SEGMENT = {v: k for k, v in SEGMENT_CODE.items()}

INTERNET_OPTIONS = ["Mobile hotspot", "Home broadband", "Business broadband", "Leased line", "Mixed per site", "None"]


@dataclass
class BusinessProfile:
    business_name: str = ""
    business_type: str = ""
    city: str = ""
    employees: int = 1
    sites: int = 1
    current_internet: str = ""
    monthly_budget: float | None = None
    monthly_telecom_spend: float | None = None
    has_gstin: bool = False
    gstin: str = ""
    gstin_status: str = "none"  # none | declared | active | cancelled | suspended | not_found | invalid
    has_udyam: bool = False
    contact_name: str = ""
    phone: str = ""
    language: str = "en"
    city_tier: int = 1
    state: str = ""
    segment: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def gstin_active(self) -> bool:
        return self.gstin_status == "active"


def city_info(city: str) -> dict | None:
    for name, info in datasets.city_directory().items():
        if name.lower() == (city or "").strip().lower():
            return {"city": name, **info}
    return None


def infer_segment(business_type: str, employees: int, sites: int) -> str:
    """Business type is the primary signal (it maps 1:1 to a segment in the leads data);
    site count overrides toward multi-site, and unknown types fall back to size."""
    mapping = datasets.business_type_segments()
    seg = mapping.get(business_type)
    if sites >= 3 and seg in (None, "Micro retail & services", "Professional offices"):
        return "Small multi-site businesses"
    if seg:
        return seg
    if sites >= 3:
        return "Small multi-site businesses"
    if employees >= 50:
        return "Small manufacturers"
    if employees >= 8:
        return "Professional offices"
    return "Micro retail & services"


def gstin_standing(gstin: str) -> str:
    """Deterministic registry lookup used for eligibility. Returns active|cancelled|suspended|not_found|invalid."""
    from .kyc.validators import is_valid_gstin
    from .kyc.registry import lookup_gstin

    g = (gstin or "").strip().upper()
    if not is_valid_gstin(g):
        return "invalid"
    rec = lookup_gstin(g)
    if rec is None:
        return "not_found"
    return rec["status"].lower()


def build_profile(data: dict) -> BusinessProfile:
    p = BusinessProfile(
        business_name=(data.get("business_name") or "").strip(),
        business_type=(data.get("business_type") or "").strip(),
        city=(data.get("city") or "").strip(),
        employees=int(data.get("employees") or 1),
        sites=int(data.get("sites") or 1),
        current_internet=data.get("current_internet") or "",
        monthly_budget=float(data["monthly_budget"]) if data.get("monthly_budget") not in (None, "") else None,
        monthly_telecom_spend=float(data["monthly_telecom_spend"]) if data.get("monthly_telecom_spend") not in (None, "") else None,
        has_gstin=bool(data.get("has_gstin")),
        gstin=(data.get("gstin") or "").strip().upper(),
        has_udyam=bool(data.get("has_udyam")),
        contact_name=(data.get("contact_name") or "").strip(),
        phone=(data.get("phone") or "").strip(),
        language=data.get("language") or "en",
    )
    info = city_info(p.city)
    p.city_tier = info["tier"] if info else int(data.get("city_tier") or 2)
    p.state = info["state"] if info else (data.get("state") or "")
    if p.gstin:
        p.gstin_status = gstin_standing(p.gstin)
    elif p.has_gstin:
        p.gstin_status = "declared"
    p.segment = infer_segment(p.business_type, p.employees, p.sites)
    return p
