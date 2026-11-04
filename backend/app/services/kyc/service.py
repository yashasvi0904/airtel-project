"""KYC case orchestration: consent, upload, OCR, verification, retention."""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import KycCase, KycDocument, Order, OrderEvent
from ..crypto import decrypt_json, encrypt_bytes, encrypt_json
from . import pipeline
from .matching import mask
from .ocr import OcrError, run_ocr
from .parsers import DOC_LABELS, DOC_TYPES, parse_document

log = logging.getLogger("kyc")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
NOTICE_VERSION = "2026-07-v1"
CONSENT_PURPOSES = [
    "Verify the identity and registrations of your business (GSTIN, Udyam) against official registries",
    "Check that the address proof matches your registered business address",
    "Create and activate your Accel Business account and services",
]


class UploadError(Exception):
    pass


def sniff_image(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    raise UploadError("Only PNG or JPG images are accepted.")


def get_or_create_case(db: Session, order: Order) -> KycCase:
    case = db.scalar(select(KycCase).where(KycCase.order_id == order.id))
    if not case:
        case = KycCase(order_id=order.id)
        db.add(case)
        db.commit()
    return case


def record_consent(db: Session, case: KycCase, order: Order, declared: dict) -> KycCase:
    case.consent = {"given_at": datetime.now(timezone.utc).isoformat(), "notice_version": NOTICE_VERSION,
                    "purposes": CONSENT_PURPOSES, "retention_days": get_settings().document_retention_days}
    case.declared = encrypt_json(declared)
    case.status = "awaiting_documents"
    order.kyc_status = "awaiting_documents"
    _event(db, order, "kyc_consent", "Consent recorded for KYC verification.", "customer")
    db.commit()
    return case


def _event(db: Session, order: Order, status: str, note: str, actor: str = "system"):
    db.add(OrderEvent(order_id=order.id, status=status, note=note, actor=actor))


def declared_of(case: KycCase) -> dict:
    return decrypt_json(case.declared) if case.declared else {}


def save_document(db: Session, case: KycCase, doc_type: str, filename: str, data: bytes) -> KycDocument:
    s = get_settings()
    if doc_type not in DOC_TYPES:
        raise UploadError(f"Unknown document type '{doc_type}'.")
    if not case.consent:
        raise UploadError("Consent must be given before uploading documents.")
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("File is larger than 8 MB.")
    sniff_image(data)
    try:
        res = run_ocr(data)
    except OcrError as e:
        raise UploadError(str(e)) from e
    ext = parse_document(doc_type, res)

    # replace an earlier upload of the same type
    for old in [d for d in case.documents if d.doc_type == doc_type]:
        _purge_file(old)
        db.delete(old)
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    path = s.upload_dir / f"{uuid.uuid4().hex}.bin"
    path.write_bytes(encrypt_bytes(data))
    doc = KycDocument(
        case_id=case.id, doc_type=doc_type, file_path=str(path), sha256=hashlib.sha256(data).hexdigest(),
        original_name=filename[:200],
        extracted=encrypt_json({"fields": ext.fields, "quality": res.quality, "notes": ext.notes, "detected": ext.detected_type}),
        purge_after=datetime.now(timezone.utc) + timedelta(days=s.document_retention_days),
    )
    db.add(doc)
    db.commit()
    db.refresh(case)
    log.info("kyc.upload case=%s type=%s sha=%s", case.id, doc_type, doc.sha256[:8])  # never log extracted values
    return doc


def verify_case(db: Session, case: KycCase, order: Order) -> dict:
    docs = db.scalars(select(KycDocument).where(KycDocument.case_id == case.id)).all()
    extracted, qualities, notes, detected = {}, {}, {}, {}
    for d in docs:
        payload = decrypt_json(d.extracted)
        extracted[d.doc_type] = payload.get("fields", {})
        qualities[d.doc_type] = payload.get("quality", {})
        notes[d.doc_type] = payload.get("notes", [])
        detected[d.doc_type] = payload.get("detected", d.doc_type)
    declared = declared_of(case)
    report = pipeline.verify(extracted, qualities, notes, detected, declared, get_settings().today)
    report["documents"] = {
        d.doc_type: {"label": DOC_LABELS[d.doc_type], "filename": d.original_name, "uploaded_at": d.uploaded_at.isoformat(),
                     "fields": pipeline.masked_fields(d.doc_type, extracted[d.doc_type]),
                     "quality": {k: v for k, v in qualities[d.doc_type].items() if k in ("blurry", "deskewed", "skew_degrees", "sharpened", "mean_confidence")},
                     "status": report["document_status"].get(d.doc_type)}
        for d in docs
    }
    case.result = report
    changed = order.kyc_status != report["status"]
    case.status = report["status"]
    order.kyc_status = report["status"]
    if changed:  # one timeline entry per status change, not per upload
        _event(db, order, f"kyc_{report['status']}", report["summary"], "system")
    if report["status"] not in ("verified", "needs_review") and order.status == "kyc_verified":
        order.status = "placed"  # a replaced document that fails re-verification pulls the order back
    if report["status"] in ("verified", "needs_review"):
        _on_kyc_ok(db, order, report["status"])
    db.commit()
    return report


def _on_kyc_ok(db: Session, order: Order, status: str):
    if status == "verified" and order.status in ("placed", "kyc_pending"):
        order.status = "kyc_verified"


def _purge_file(doc: KycDocument):
    if doc.file_path:
        try:
            from pathlib import Path

            Path(doc.file_path).unlink(missing_ok=True)
        except OSError:
            log.warning("kyc.purge failed for doc %s", doc.id)
        doc.file_path = None


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Delete stored files whose retention period has elapsed (extracted data is dropped with them)."""
    now = now or datetime.now(timezone.utc)
    n = 0
    for d in db.scalars(select(KycDocument).where(KycDocument.file_path.is_not(None))):
        pa = d.purge_after
        if pa is not None and pa.tzinfo is None:
            pa = pa.replace(tzinfo=timezone.utc)
        if pa and pa <= now:
            _purge_file(d)
            d.extracted = {}
            n += 1
    db.commit()
    return n


def erase_case(db: Session, case: KycCase) -> int:
    """Right-to-erasure: remove all stored files and extracted data for a case."""
    n = 0
    for d in list(case.documents):
        _purge_file(d)
        db.delete(d)
        n += 1
    case.declared, case.result, case.consent = {}, {}, {**(case.consent or {}), "withdrawn": datetime.now(timezone.utc).isoformat()}
    case.status = "erased"
    db.commit()
    return n


def public_case(case: KycCase, db: Session) -> dict:
    docs = db.scalars(select(KycDocument).where(KycDocument.case_id == case.id)).all()
    declared = declared_of(case)
    return {
        "case_id": case.id, "status": case.status, "consent": case.consent or None,
        "required_documents": pipeline.required_documents(declared) if case.consent else list(DOC_TYPES),
        "uploaded": {d.doc_type: {"filename": d.original_name, "uploaded_at": d.uploaded_at.isoformat(),
                                  "purge_after": d.purge_after.isoformat() if d.purge_after else None} for d in docs},
        "declared": {k: (mask(str(v), 2, 3) if k in ("gstin", "udyam_number") and v else v) for k, v in declared.items()},
        "result": case.result or None,
    }
