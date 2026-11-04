"""Name and address fuzzy matching tolerant of OCR noise (dropped spaces, truncated lines)."""
import re

from rapidfuzz import fuzz

_SUFFIXES = ("private limited", "pvt ltd", "pvt. ltd.", "limited", "ltd", "llp")
_PROP = re.compile(r"\(\s*prop\.?\s*(.*?)\s*\)\s*$", re.IGNORECASE)


def norm_name(s: str) -> str:
    """Lower-case alphanumerics only, so 'Vindhya Tours&Travels' == 'VindhyaTours & Travels'."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def strip_proprietor(legal_name: str) -> tuple[str, str]:
    """'Neha Kaur (Prop. Vindhya Tours & Travels)' -> ('Neha Kaur', 'Vindhya Tours & Travels')."""
    m = _PROP.search(legal_name or "")
    if not m:
        return "", legal_name or ""
    return (legal_name[: m.start()].strip(), m.group(1).strip())


def name_similarity(a: str, b: str) -> float:
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    return fuzz.ratio(na, nb)


def same_entity_suffix(a: str, b: str) -> bool:
    """True when two names differ only by a legal suffix (Pvt Ltd / LLP) - these are different registrations."""
    sa = norm_name(a)
    sb = norm_name(b)
    if sa == sb:
        return True
    for suf in ("pvtltd", "llp", "limited", "ltd"):
        if sa.endswith(suf) != sb.endswith(suf):
            return False
    return True


def _addr_core(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"shop\s*/?\s*unit", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def pincode(s: str) -> str:
    m = re.findall(r"(\d{6})", re.sub(r"[\s\-]", "", s or ""))
    return m[-1] if m else ""


def address_similarity(a: str, b: str) -> float:
    ca, cb = _addr_core(a), _addr_core(b)
    if not ca or not cb:
        return 0.0
    return fuzz.ratio(ca, cb)


def name_match(a: str, b: str, threshold: float = 88) -> bool:
    return name_similarity(a, b) >= threshold


def mask(value: str, keep_start: int = 2, keep_end: int = 3) -> str:
    v = value or ""
    if len(v) <= keep_start + keep_end:
        return "*" * len(v)
    return v[:keep_start] + "*" * (len(v) - keep_start - keep_end) + v[-keep_end:]
