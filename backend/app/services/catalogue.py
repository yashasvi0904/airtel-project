"""Product catalogue: seeded from product_catalogue.csv into the DB, served from the DB."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product
from . import datasets


def _split(value: str, sep: str) -> list[str]:
    return [v.strip() for v in str(value).split(sep) if v.strip()]


def seed_catalogue(db: Session) -> int:
    """Insert/refresh catalogue rows from the CSV. The CSV is the single source of truth for prices and rules."""
    df = datasets.catalogue_frame()
    for r in df.to_dict("records"):
        row = Product(
            product_id=r["product_id"],
            category=r["category"],
            product_name=r["product_name"],
            description=r["description"],
            unit=r["unit"],
            price_min=float(r["price_min_inr_per_month"]),
            price_max=float(r["price_max_inr_per_month"]),
            setup_fee=float(r["one_time_setup_inr"]),
            min_contract_months=int(r["min_contract_months"]),
            city_tiers=[int(t) for t in _split(r["available_city_tiers"], ";")],
            min_employees=int(r["min_employees"]),
            min_sites=int(r["min_sites"]),
            requires_gstin=str(r["requires_gstin"]).upper() == "Y",
            requires_one_of=_split(r["requires_one_of"], "|"),
            install_days=int(r["typical_install_days"]),
            target_segments=_split(r["target_segments"], ";"),
        )
        db.merge(row)
    db.commit()
    return len(df)


def all_products(db: Session) -> dict[str, Product]:
    return {p.product_id: p for p in db.scalars(select(Product).order_by(Product.product_id))}


def product_dict(p: Product) -> dict:
    return {
        "product_id": p.product_id,
        "category": p.category,
        "name": p.product_name,
        "description": p.description,
        "unit": p.unit,
        "price_min": p.price_min,
        "price_max": p.price_max,
        "setup_fee": p.setup_fee,
        "min_contract_months": p.min_contract_months,
        "city_tiers": p.city_tiers,
        "min_employees": p.min_employees,
        "min_sites": p.min_sites,
        "requires_gstin": p.requires_gstin,
        "requires_one_of": p.requires_one_of,
        "install_days": p.install_days,
        "target_segments": p.target_segments,
    }
