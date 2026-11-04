"""Auth, catalogue/meta and the mock GSTIN / Udyam registry APIs."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Product, User
from ..config import get_settings
from ..schemas import GoogleIn, LoginIn, RegisterIn
from ..security import auth_limiter, create_token, current_user, hash_password, verify_password
from ..services import analytics, datasets
from ..services.google_auth import GoogleAuthError, verify_google_token
from ..services.catalogue import product_dict
from ..services.kyc import registry
from ..services.kyc.matching import mask
from ..services.kyc.validators import gstin_checksum_char, gstin_format_ok, is_valid_gstin, is_valid_udyam, normalise_udyam
from ..services.profile import INTERNET_OPTIONS, SEGMENTS

router = APIRouter(prefix="/api")


def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "phone": u.phone, "role": u.role}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/auth/register", status_code=201, dependencies=[Depends(auth_limiter)])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "An account with this email already exists")
    u = User(email=body.email, name=body.name.strip(), phone=body.phone, password_hash=hash_password(body.password), role="customer")
    db.add(u)
    db.commit()
    return {"token": create_token(u), "user": user_dict(u)}


@router.post("/auth/login", dependencies=[Depends(auth_limiter)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(u), "user": user_dict(u)}


@router.get("/auth/config")
def auth_config():
    """Public sign-in options for the UI (a Google client ID is public by design, not a secret)."""
    return {"google_client_id": get_settings().google_client_id or None}


@router.post("/auth/google", dependencies=[Depends(auth_limiter)])
def google_sign_in(body: GoogleIn, db: Session = Depends(get_db)):
    """Sign in or sign up with a Google ID token. The token is verified server-side; only verified emails are accepted."""
    try:
        info = verify_google_token(body.credential)
    except GoogleAuthError as e:
        raise HTTPException(401, str(e)) from e
    email = info["email"].lower()
    u = db.scalar(select(User).where(User.email == email))
    created = False
    if not u:
        # random, unusable password hash: this account signs in with Google (a password can be set later via reset)
        u = User(email=email, name=(info.get("name") or email.split("@")[0])[:120], password_hash=hash_password(secrets.token_urlsafe(32)), role="customer")
        db.add(u)
        db.commit()
        created = True
    return {"token": create_token(u), "user": user_dict(u), "created": created}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


@router.get("/meta")
def meta():
    cities = [{"city": c, **info} for c, info in sorted(datasets.city_directory().items())]
    types = [{"business_type": t, "segment": s} for t, s in sorted(datasets.business_type_segments().items())]
    return {"cities": cities, "business_types": types, "internet_options": INTERNET_OPTIONS, "segments": SEGMENTS,
            "languages": [{"code": "en", "label": "English"}, {"code": "hi", "label": "हिन्दी"}],
            "benchmarks": datasets.segment_benchmarks()}


@router.get("/catalogue")
def catalogue(db: Session = Depends(get_db)):
    return [product_dict(p) for p in db.scalars(select(Product).order_by(Product.product_id))]


# ---- Mock registries (emulate the external GST / Udyam lookup APIs; backed by the supplied CSVs)

@router.get("/registry/gstin/{gstin}", dependencies=[Depends(auth_limiter)])
def lookup_gstin(gstin: str):
    g = gstin.strip().upper()
    res = {"gstin": mask(g), "format_valid": gstin_format_ok(g), "checksum_valid": is_valid_gstin(g)}
    if res["format_valid"] and not res["checksum_valid"]:
        res["expected_check_digit"] = gstin_checksum_char(g[:14])
    rec = registry.lookup_gstin(g) if res["checksum_valid"] else None
    res["found"] = rec is not None
    if rec:
        res.update(legal_name=rec["legal_name"], trade_name=rec["trade_name"], constitution=rec["constitution"], state=rec["state"],
                   status=rec["status"], registration_date=rec["registration_date"], address=rec["principal_place_of_business"])
    return res


@router.get("/registry/udyam/{number}", dependencies=[Depends(auth_limiter)])
def lookup_udyam(number: str):
    n = normalise_udyam(number)
    res = {"udyam_number": mask(n, 9, 3), "format_valid": is_valid_udyam(n)}
    rec = registry.lookup_udyam(n) if res["format_valid"] else None
    res["found"] = rec is not None
    if rec:
        res.update(enterprise_name=rec["enterprise_name"], enterprise_type=rec["enterprise_type"], major_activity=rec["major_activity"],
                   city=rec["city"], state=rec["state"], date_of_registration=rec["date_of_registration"])
    return res


@router.get("/public/stats")
def public_stats():
    """Landing-page proof points computed from the supplied dataset."""
    k = analytics.kpis()
    return {"leads": k["leads"], "avg_days_to_activation": k["avg_days_to_activation"], "follow_up_calls": k["avg_follow_up_calls"],
            "products": 25}


# ---- Demo helper: serve the supplied specimen KYC images so the UI can load a sample applicant

@router.get("/demo/kyc-samples")
def kyc_samples():
    from ..config import get_settings

    root = get_settings().data_dir / "kyc_documents"
    out = {}
    for f in sorted(root.glob("K*_*.png")):
        k, doc = f.stem.split("_", 1)
        out.setdefault(k, []).append(doc)
    return {"applicants": [{"id": k, "documents": docs} for k, docs in out.items()],
            "note": "Specimen documents supplied with the hackathon dataset. All fictional."}


@router.get("/demo/kyc-samples/{applicant}/{doc}")
def kyc_sample_file(applicant: str, doc: str):
    import re

    from fastapi.responses import FileResponse

    from ..config import get_settings

    if not re.fullmatch(r"K\d{2}", applicant) or not re.fullmatch(r"[a-z_]+", doc):
        raise HTTPException(404, "Sample not found")
    f = get_settings().data_dir / "kyc_documents" / f"{applicant}_{doc}.png"
    if not f.exists():
        raise HTTPException(404, "Sample not found")
    return FileResponse(f, media_type="image/png")
