"""Mock GSTIN / Udyam registries backed by the supplied CSV files (read-only)."""
from functools import lru_cache

from .. import datasets
from .matching import norm_name
from .validators import normalise_udyam


@lru_cache
def _gstin_index() -> dict[str, dict]:
    return {r["gstin"]: r for r in datasets.gstin_registry().to_dict("records")}


@lru_cache
def _udyam_index() -> dict[str, dict]:
    return {r["udyam_number"]: r for r in datasets.udyam_registry().to_dict("records")}


@lru_cache
def _udyam_by_name() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for r in datasets.udyam_registry().to_dict("records"):
        idx.setdefault(norm_name(r["enterprise_name"]), []).append(r)
    return idx


def lookup_gstin(gstin: str) -> dict | None:
    return _gstin_index().get((gstin or "").strip().upper())


def lookup_udyam(number: str) -> dict | None:
    return _udyam_index().get(normalise_udyam(number))


def find_udyam_candidates(enterprise_name: str, city: str = "", state: str = "") -> list[dict]:
    """Composite lookup used when the certificate does not print a number: name + city (+ state)."""
    rows = _udyam_by_name().get(norm_name(enterprise_name), [])
    if city:
        c = norm_name(city)
        rows = [r for r in rows if norm_name(r["city"]) == c] or []
    if state and len(rows) > 1:
        s = norm_name(state)
        rows = [r for r in rows if norm_name(r["state"]) == s] or rows
    return rows
