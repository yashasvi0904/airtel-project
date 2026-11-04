"""Back-office analytics over the supplied leads dataset (pandas) plus a simple propensity model."""
from functools import lru_cache

import numpy as np
import pandas as pd

from . import datasets

STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
STAGE_DATE_COL = {"Contacted": "contacted_date", "Needs assessed": "needs_assessed_date", "Quote accepted": "quote_accepted_date",
                  "KYC complete": "kyc_complete_date", "Activated": "activated_date"}


def _reached(df: pd.DataFrame) -> dict[str, int]:
    rank = {s: i for i, s in enumerate(STAGES)}
    r = df["stage_reached"].map(rank)
    return {s: int((r >= i).sum()) for i, s in enumerate(STAGES)}


def funnel(df: pd.DataFrame | None = None) -> list[dict]:
    df = datasets.leads() if df is None else df
    reached = _reached(df)
    out, prev = [], None
    for s in STAGES:
        n = reached[s]
        out.append({"stage": s, "count": n, "pct_of_previous": round(100 * n / prev, 1) if prev else None,
                    "pct_of_leads": round(100 * n / reached["Lead"], 1) if reached["Lead"] else 0})
        prev = n
    return out


def kpis() -> dict:
    df = datasets.leads()
    act = df[df["activated"]]
    return {
        "leads": int(len(df)), "activated": int(len(act)),
        "lead_to_activation_pct": round(100 * len(act) / len(df), 2),
        "avg_days_to_activation": round(float(act["days_lead_to_activation"].mean()), 1),
        "avg_follow_up_calls": round(float(act["customer_follow_up_calls"].mean()), 2),
        "cac_per_activated_inr": round(float(df["acquisition_cost_inr"].sum() / len(act))),
        "median_monthly_bundle_inr": float(act["monthly_bundle_value_inr"].median()),
        "mean_monthly_bundle_inr": round(float(act["monthly_bundle_value_inr"].mean())),
        "churn_6m_pct": round(100 * float((act["churned_within_6_months"] == "Y").mean()), 1),
        "avg_nps": round(float(act["nps_score"].mean()), 2),
        "activation_with_gstin_pct": round(100 * float(df[df["has_gstin"] == "Y"]["activated"].mean()), 1),
        "activation_without_gstin_pct": round(100 * float(df[df["has_gstin"] == "N"]["activated"].mean()), 1),
    }


def _group(col: str) -> list[dict]:
    df = datasets.leads()
    rows = []
    for key, g in df.groupby(col):
        a = g[g["activated"]]
        rows.append({
            "key": str(key), "leads": int(len(g)), "activated": int(len(a)), "conversion_pct": round(100 * len(a) / len(g), 1),
            "avg_cac_inr": round(float(g["acquisition_cost_inr"].mean())),
            "avg_monthly_value_inr": round(float(a["monthly_bundle_value_inr"].mean())) if len(a) else 0,
            "churn_pct": round(100 * float((a["churned_within_6_months"] == "Y").mean()), 1) if len(a) else None,
            "avg_nps": round(float(a["nps_score"].mean()), 1) if len(a) else None,
            "avg_days": round(float(a["days_lead_to_activation"].mean()), 1) if len(a) else None,
            "revenue_monthly_inr": round(float(a["monthly_bundle_value_inr"].sum())),
        })
    return sorted(rows, key=lambda r: -r["leads"])


def segments() -> list[dict]:
    rows = _group("segment")
    total = sum(r["leads"] for r in rows)
    for r in rows:
        r["share_pct"] = round(100 * r["leads"] / total, 1)
        # revenue per rupee of acquisition spend - used to prioritise segments
        spend = float(datasets.leads().query("segment == @r['key']")["acquisition_cost_inr"].sum())
        r["monthly_revenue_per_acq_inr"] = round(r["revenue_monthly_inr"] / spend, 2) if spend else None
    return rows


def breakdown(by: str) -> list[dict]:
    allowed = {"source": "lead_source", "language": "preferred_language", "gstin": "has_gstin", "tier": "city_tier",
               "internet": "current_internet", "turnover": "annual_turnover_band", "city": "city", "business_type": "business_type"}
    if by not in allowed:
        raise ValueError("unknown breakdown")
    return _group(allowed[by])


def drop_reasons() -> list[dict]:
    df = datasets.leads()
    d = df[df["outcome"] == "Dropped"]
    out = []
    for (reason, stage), n in d.groupby(["drop_reason", "stage_reached"]).size().items():
        out.append({"reason": reason, "stage": stage, "count": int(n)})
    return sorted(out, key=lambda r: -r["count"])


def weekly_trend() -> list[dict]:
    df = datasets.leads().copy()
    df["created"] = pd.to_datetime(df["created_date"])
    df["week"] = df["created"].dt.to_period("W").apply(lambda p: p.start_time.date().isoformat())
    g = df.groupby("week").agg(leads=("lead_id", "count"), activated=("activated", "sum"))
    return [{"week": w, "leads": int(r.leads), "activated": int(r.activated)} for w, r in g.iterrows()]


def product_attach() -> list[dict]:
    df = datasets.leads()
    act = df[df["activated"]]
    counts: dict[str, int] = {}
    rev: dict[str, float] = {}
    cat = datasets.catalogue_frame().set_index("product_id")
    for b in act["bundle_products"].dropna():
        for it in b.split(";"):
            pid, q = it.split("x")
            counts[pid] = counts.get(pid, 0) + 1
            row = cat.loc[pid]
            rev[pid] = rev.get(pid, 0) + int(q) * (row["price_min_inr_per_month"] + row["price_max_inr_per_month"]) / 2
    return sorted(({"product_id": p, "name": cat.loc[p, "product_name"], "customers": c, "attach_pct": round(100 * c / len(act), 1),
                    "est_monthly_revenue_inr": round(rev[p])} for p, c in counts.items()), key=lambda r: -r["customers"])


# ------------------------------------------------------------------ propensity model

CAT_FEATURES = ["segment", "lead_source", "city_tier", "annual_turnover_band", "has_gstin", "has_udyam", "current_internet", "preferred_language"]
NUM_FEATURES = ["employee_count", "num_sites", "monthly_telecom_spend_inr"]


def _features(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    X = pd.get_dummies(df[CAT_FEATURES].astype(str), dtype=float)
    X["log_emp"] = np.log1p(df["employee_count"])
    X["log_sites"] = np.log1p(df["num_sites"])
    X["log_spend"] = np.log1p(df["monthly_telecom_spend_inr"])
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X


@lru_cache
def propensity_model() -> dict:
    """Logistic regression on lead profile only (no funnel-stage leakage). Reports hold-out AUC."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    df = datasets.leads()
    X, y = _features(df), df["activated"].astype(int)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced").fit(scaler.transform(Xtr), ytr)
    auc = float(roc_auc_score(yte, clf.predict_proba(scaler.transform(Xte))[:, 1]))
    coefs = sorted(zip(X.columns, clf.coef_[0]), key=lambda kv: -abs(kv[1]))[:12]
    # refit on everything for scoring
    scaler = StandardScaler().fit(X)
    clf = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced").fit(scaler.transform(X), y)
    return {"clf": clf, "scaler": scaler, "columns": list(X.columns), "auc": round(auc, 3),
            "top_drivers": [{"feature": f, "weight": round(float(w), 3)} for f, w in coefs]}


def score_frame(df: pd.DataFrame) -> np.ndarray:
    m = propensity_model()
    X = _features(df, m["columns"])
    p = m["clf"].predict_proba(m["scaler"].transform(X))[:, 1]
    # class_weight='balanced' inflates probabilities; rescale to a 0-100 percentile-like score against the base population
    return p


@lru_cache
def scored_leads() -> pd.DataFrame:
    df = datasets.leads().copy()
    p = score_frame(df)
    df["propensity"] = (100 * pd.Series(p).rank(pct=True).values).round(0).astype(int)
    return df


def leads_page(page: int = 1, size: int = 25, segment: str | None = None, source: str | None = None, stage: str | None = None,
               q: str | None = None, sort: str = "propensity", open_only: bool = False) -> dict:
    df = scored_leads()
    if segment:
        df = df[df["segment"] == segment]
    if source:
        df = df[df["lead_source"] == source]
    if stage:
        df = df[df["stage_reached"] == stage]
    if open_only:  # dropped before quote - candidates for re-engagement
        df = df[(df["outcome"] == "Dropped") & (df["stage_reached"].isin(["Contacted", "Needs assessed"]))]
    if q:
        ql = q.lower()
        df = df[df["business_name"].str.lower().str.contains(ql, na=False) | df["lead_id"].str.lower().str.contains(ql, na=False)
                | df["city"].str.lower().str.contains(ql, na=False)]
    if sort in df.columns:
        df = df.sort_values(sort, ascending=sort in ("lead_id",))
    total = len(df)
    sl = df.iloc[(page - 1) * size: page * size]
    cols = ["lead_id", "business_name", "business_type", "segment", "city", "lead_source", "stage_reached", "outcome", "drop_reason",
            "employee_count", "num_sites", "has_gstin", "propensity", "monthly_telecom_spend_inr", "preferred_language"]
    return {"total": int(total), "page": page, "size": size, "items": sl[cols].fillna("").to_dict("records")}


@lru_cache
def _base_scores() -> np.ndarray:
    return score_frame(datasets.leads())


def propensity_for_profile(profile: dict, segment: str, city_tier: int) -> int:
    """Score a live journey against the historical population (0-100 percentile)."""
    row = pd.DataFrame([{
        "segment": segment, "lead_source": "Website form", "city_tier": city_tier,
        "annual_turnover_band": "40 lakh - 1.5 cr", "has_gstin": "Y" if profile.get("has_gstin") else "N",
        "has_udyam": "Y" if profile.get("has_udyam") else "N", "current_internet": profile.get("current_internet") or "Mobile hotspot",
        "preferred_language": {"hi": "Hindi", "en": "English"}.get(profile.get("language", "en"), "English"),
        "employee_count": profile.get("employees", 1), "num_sites": profile.get("sites", 1),
        "monthly_telecom_spend_inr": profile.get("monthly_telecom_spend") or profile.get("monthly_budget") or 1000,
    }])
    p = float(score_frame(row)[0])
    return int(round(100 * float((_base_scores() < p).mean())))
