"""Read-only loaders for the supplied CSV datasets (never modified, never written back)."""
from functools import lru_cache

import pandas as pd

from ..config import get_settings


def _path(name: str):
    return get_settings().data_dir / name


@lru_cache
def leads() -> pd.DataFrame:
    df = pd.read_csv(_path("smb_leads.csv"))
    df["activated"] = df["outcome"] == "Activated"
    return df


@lru_cache
def gstin_registry() -> pd.DataFrame:
    return pd.read_csv(_path("mock_gstin_registry.csv"), dtype=str).fillna("")


@lru_cache
def udyam_registry() -> pd.DataFrame:
    return pd.read_csv(_path("mock_udyam_registry.csv"), dtype=str).fillna("")


@lru_cache
def catalogue_frame() -> pd.DataFrame:
    return pd.read_csv(_path("product_catalogue.csv"), dtype={"available_city_tiers": str}).fillna("")


@lru_cache
def business_type_segments() -> dict[str, str]:
    """business_type -> segment, derived from the leads (each type maps to exactly one segment)."""
    df = leads()
    return df.groupby("business_type")["segment"].agg(lambda s: s.value_counts().index[0]).to_dict()


@lru_cache
def city_directory() -> dict[str, dict]:
    """city -> {tier, state}, derived from the leads."""
    df = leads()
    out = {}
    for city, grp in df.groupby("city"):
        out[city] = {"tier": int(grp["city_tier"].iloc[0]), "state": grp["state"].iloc[0]}
    return out


@lru_cache
def segment_attach_rates() -> dict[str, dict[str, float]]:
    """segment -> product_id -> share of activated customers in that segment who bought it."""
    df = leads()
    act = df[df["activated"]]
    rates: dict[str, dict[str, float]] = {}
    for seg, grp in act.groupby("segment"):
        counts: dict[str, int] = {}
        for bundle in grp["bundle_products"].dropna():
            for item in bundle.split(";"):
                pid = item.split("x")[0]
                counts[pid] = counts.get(pid, 0) + 1
        rates[seg] = {pid: round(c / len(grp), 3) for pid, c in counts.items()}
    return rates


@lru_cache
def segment_benchmarks() -> dict[str, dict]:
    """Median monthly bundle value etc. for activated customers by segment (used for budget sanity messages)."""
    df = leads()
    act = df[df["activated"]]
    out = {}
    for seg, grp in act.groupby("segment"):
        out[seg] = {
            "activated": int(len(grp)),
            "median_monthly_value": float(grp["monthly_bundle_value_inr"].median()),
            "median_setup": float(grp["one_time_setup_inr"].median()),
            "avg_days_to_activation": round(float(grp["days_lead_to_activation"].mean()), 1),
        }
    return out
