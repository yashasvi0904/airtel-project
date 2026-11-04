"""Smart KYC against the 12 specimen applicants (K01-K12). Expected outcomes come from inspecting the images and
registries by hand; there is no official answer key in the student pack."""
import os
from datetime import date

import pytest

from app.config import get_settings
from app.services.kyc import registry
from app.services.kyc.matching import address_similarity, name_match, strip_proprietor
from app.services.kyc.ocr import OcrError, run_ocr
from app.services.kyc.parsers import DOC_TYPES, parse_document
from app.services.kyc.pipeline import required_documents, verify

DOCS = get_settings().data_dir / "kyc_documents"
TODAY = date(2026, 7, 15)


@pytest.fixture(scope="module")
def reports():
    out = {}
    for k in range(1, 13):
        ex, ql, nt, dt = {}, {}, {}, {}
        for d in DOC_TYPES:
            f = DOCS / f"K{k:02d}_{d}.png"
            if not f.exists():
                continue
            res = run_ocr(f.read_bytes())
            e = parse_document(d, res)
            ex[d], ql[d], nt[d], dt[d] = e.fields, res.quality, e.notes, e.detected_type
        out[k] = verify(ex, ql, nt, dt, {"has_gstin": True, "has_udyam": True}, TODAY)
    return out


def codes(rep):
    return {i["code"] for i in rep["issues"]}


@pytest.mark.parametrize("k", [2, 3, 8, 9, 10, 12])
def test_clean_applicants_verify(reports, k):
    assert reports[k]["status"] == "verified", reports[k]["issues"]
    assert reports[k]["registry"]["gstin"]["status"] == "Active"


def test_k01_cancelled_gstin_and_unknown_udyam(reports):
    r = reports[1]
    assert r["status"] == "rejected"
    assert {"gstin_cancelled", "udyam_not_found"} <= codes(r)


def test_k02_rotated_scan_is_straightened_and_read(reports):
    r = reports[2]
    assert any(c["id"] == "deskew" for c in r["checks"])
    assert r["status"] == "verified"


def test_k04_blurry_certificate_asks_for_reupload(reports):
    r = reports[4]
    assert r["status"] == "action_required" and "unreadable_document" in codes(r)
    assert r["document_status"]["gst_certificate"] == "failed"


def test_k05_missing_udyam_certificate(reports):
    r = reports[5]
    assert r["status"] == "incomplete"
    assert codes(r) == {"missing_document"} and r["document_status"]["udyam_certificate"] == "missing"


def test_k06_tampered_gstin_fails_checksum_and_points_to_registry_match(reports):
    r = reports[6]
    assert r["status"] == "rejected" and "gstin_invalid" in codes(r)
    assert "looks altered" in next(i["message"] for i in r["issues"] if i["code"] == "gstin_invalid")


def test_k07_legal_name_differs_from_registry_goes_to_manual_review(reports):
    r = reports[7]
    assert r["status"] == "needs_review" and codes(r) == {"gst_legal_name_mismatch"}


def test_k11_stale_address_proof(reports):
    r = reports[11]
    assert r["status"] == "action_required" and codes(r) == {"address_proof_stale"}
    assert "257 days" in r["issues"][0]["message"]


def test_masked_identifiers_in_report(reports):
    blob = str(reports[3])
    assert "27XUIXG0767D1ZP" not in blob and "UDYAM-MH-00-9516696" not in blob
    assert "27*" in blob


# ------------------------------------------------------------------ units

def test_required_documents_policy():
    assert required_documents({"has_gstin": True, "has_udyam": True}) == ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
    assert "udyam_certificate" not in required_documents({"has_gstin": True, "has_udyam": False})
    assert "gst_certificate" in required_documents({"has_gstin": False, "has_udyam": False})  # one business proof is mandatory


def test_name_matching_tolerates_ocr_spacing_but_not_different_names():
    assert name_match("VindhyaTours&Travels", "Vindhya Tours & Travels")
    assert not name_match("Shri Physio Clinic", "Neelgiri Physio Clinic")
    assert strip_proprietor("Neha Kaur (Prop. Vindhya Tours & Travels)") == ("Neha Kaur", "Vindhya Tours & Travels")


def test_address_similarity_handles_wrapped_text():
    a = "Shop/Unit 1, Tech Park Road, Visakhapatnam, Andhra Pradesh - 118383"
    assert address_similarity(a, a.replace(" ", "")) > 95
    assert address_similarity(a, "Shop/Unit 9, MG Road, Mumbai, Maharashtra - 400001") < 70


def test_udyam_lookup_by_details_when_number_not_printed():
    assert len(registry.find_udyam_candidates("Ganesh Woodcraft", "Nagpur", "Maharashtra")) == 1
    assert registry.find_udyam_candidates("Vindhya Tours & Travels", "Visakhapatnam") == []


def test_non_image_upload_rejected():
    with pytest.raises(OcrError):
        run_ocr(b"%PDF-1.4 not an image")
