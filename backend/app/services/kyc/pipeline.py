"""Deterministic KYC verification. OCR output goes in; checks, issues and a status come out.

Nothing here calls an LLM: every outcome is derived from registry lookups, validators and fuzzy matching, and each
check carries a human-readable explanation so the applicant knows exactly what to fix.
"""
from dataclasses import dataclass, field
from datetime import date

from . import registry
from .matching import (address_similarity, mask, name_match, name_similarity, norm_name, pincode, same_entity_suffix,
                       strip_proprietor)
from .parsers import DOC_LABELS, DOC_TYPES
from .validators import gstin_checksum_char, gstin_format_ok, is_valid_gstin, is_valid_udyam, normalise_udyam, parse_date

ADDRESS_PROOF_MAX_AGE_DAYS = 90
NAME_THRESHOLD = 88
ADDRESS_THRESHOLD = 88
AUTHORISED_DESIGNATIONS = {"owner", "partner", "director", "proprietor", "managing director"}

# issue severities -> resulting case status
REJECT, FIX, REVIEW = "reject", "fix", "review"


@dataclass
class Check:
    id: str
    label: str
    status: str  # pass | fail | warn | info
    detail: str
    doc: str | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status, "detail": self.detail, "doc": self.doc}


@dataclass
class Issue:
    code: str
    severity: str  # reject | fix | review
    doc: str | None
    message: str
    action: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "doc": self.doc, "message": self.message, "action": self.action}


@dataclass
class Ctx:
    today: date
    checks: list[Check] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def check(self, id, label, ok, detail_ok, detail_bad, doc=None, warn=False):
        status = "pass" if ok else ("warn" if warn else "fail")
        self.checks.append(Check(id, label, status, detail_ok if ok else detail_bad, doc))
        return ok

    def info(self, id, label, detail, doc=None):
        self.checks.append(Check(id, label, "info", detail, doc))

    def issue(self, code, severity, doc, message, action):
        self.issues.append(Issue(code, severity, doc, message, action))


def required_documents(declared: dict) -> list[str]:
    """All four documents are requested unless the business states it has no GSTIN / Udyam registration."""
    req = ["signatory_id", "address_proof"]
    if declared.get("has_gstin", True) or declared.get("needs_gstin", False):
        req.append("gst_certificate")
    if declared.get("has_udyam", True):
        req.append("udyam_certificate")
    if not any(d in req for d in ("gst_certificate", "udyam_certificate")):
        req.append("gst_certificate")  # at least one business registration proof is mandatory
    return [d for d in DOC_TYPES if d in req]


def masked_fields(doc_type: str, f: dict) -> dict:
    out = dict(f)
    for k, keep in (("gstin", (2, 3)), ("udyam_number", (9, 3)), ("id_number", (7, 2)), ("consumer_no", (0, 3))):
        if out.get(k):
            out[k] = mask(out[k], *keep)
    return out


# ---------------------------------------------------------------- per-document checks

def _quality(ctx: Ctx, doc: str, q: dict, fields: dict, notes: list[str]):
    blurry, readable = q.get("blurry"), len([v for v in fields.values() if v]) >= 3
    if q.get("deskewed"):
        ctx.info("deskew", "Image alignment", f"Document was tilted {q.get('skew_degrees')}° and was straightened automatically.", doc)
    if blurry and not readable:
        ctx.check("readable", "Image is readable", False, "", "The image is too blurry to read reliably.", doc)
        ctx.issue("unreadable_document", FIX, doc, f"The {DOC_LABELS[doc]} is too blurry for us to read.",
                  "Re-upload a sharp, well-lit photo or scan of the full document.")
        return False
    if blurry:
        ctx.check("readable", "Image is readable", False, "", "The image is slightly blurry; extraction confidence is reduced.", doc, warn=True)
    else:
        ctx.check("readable", "Image is readable", True, "Text was extracted clearly.", "", doc)
    for n in notes:
        ctx.info("ocr_note", "OCR correction", n, doc)
    return True


def _legal_name_match(cert: str, reg: str) -> bool:
    """Compare owner and business parts separately so '(Prop. Shri Physio)' vs '(Prop. Neelgiri Physio)' is caught."""
    (o1, b1), (o2, b2) = strip_proprietor(cert), strip_proprietor(reg)
    if o1 or o2:
        return name_match(o1, o2, 90) and name_match(b1, b2, 90)
    return name_match(cert, reg, 92)


def _nearest_gstin(g: str) -> str | None:
    """If a number fails its checksum, find a registry GSTIN differing in <=2 characters (tampered/mistyped digit)."""
    from .. import datasets

    if len(g) != 15:
        return None
    for cand in datasets.gstin_registry()["gstin"]:
        if sum(a != b for a, b in zip(cand, g)) <= 2:
            return cand
    return None


def _check_gst(ctx: Ctx, f: dict, declared: dict):
    d = "gst_certificate"
    g = (f.get("gstin") or "").upper()
    if not g:
        ctx.check("gstin_present", "GSTIN found on certificate", False, "", "No GSTIN could be read from the certificate.", d)
        ctx.issue("gstin_missing", FIX, d, "We could not read a GSTIN on the certificate.", "Upload a clearer copy of the GST certificate.")
        return None
    ctx.check("gstin_format", "GSTIN format", gstin_format_ok(g), f"{mask(g)} has a valid 15-character structure.",
              f"{mask(g)} is not a valid GSTIN structure.", d)
    ok_sum = is_valid_gstin(g)
    ctx.check("gstin_checksum", "GSTIN checksum", ok_sum, "Checksum digit is correct.",
              f"Checksum digit should be {gstin_checksum_char(g[:14]) if len(g) >= 14 else '?'} - the number is mistyped or altered.", d)
    if not ok_sum:
        near = _nearest_gstin(g)
        hint = f" It is 1-2 characters away from registered GSTIN {mask(near)}, so it looks altered or mistyped." if near else ""
        ctx.issue("gstin_invalid", REJECT, d, "The GSTIN on the certificate fails the checksum, so it cannot be a genuine number." + hint,
                  "Check the GSTIN and upload the correct certificate.")
        return None
    dec = (declared.get("gstin") or "").upper()
    if dec:
        same = dec == g
        ctx.check("gstin_declared", "Matches GSTIN you entered", same, "Entered GSTIN equals the certificate.",
                  f"You entered {mask(dec)} but the certificate shows {mask(g)}.", d)
        if not same:
            ctx.issue("gstin_declared_mismatch", FIX, d, "The GSTIN you entered differs from the one on the certificate.", "Correct the GSTIN or upload the right certificate.")
    rec = registry.lookup_gstin(g)
    if not rec:
        ctx.check("gstin_registry", "Found in GST registry", False, "", f"{mask(g)} was not found in the GST registry.", d)
        ctx.issue("gstin_not_found", REJECT, d, "This GSTIN does not exist in the GST registry.", "Provide a valid GSTIN or continue with products that do not need one.")
        return None
    ctx.check("gstin_registry", "Found in GST registry", True, f"Registered to {rec['trade_name']}.", "", d)
    active = rec["status"] == "Active"
    ctx.check("gstin_active", "GSTIN is active", active, "Registration status is Active.",
              f"Registration is {rec['status']} in the GST registry.", d)
    if not active:
        ctx.issue(f"gstin_{rec['status'].lower()}", REJECT, d, f"This GSTIN is {rec['status'].lower()}; products that require an active GSTIN cannot be sold.",
                  "Reinstate the registration or remove GSTIN-only products from your order.")
    # certificate vs registry
    legal_ok = _legal_name_match(f.get("legal_name", ""), rec["legal_name"])
    ctx.check("gst_name_registry", "Legal name matches registry", legal_ok, "Legal name matches the registry record.",
              f"Certificate says '{f.get('legal_name')}', registry says '{rec['legal_name']}'.", d)
    if not legal_ok:
        ctx.issue("gst_legal_name_mismatch", REVIEW, d, "The legal name on the certificate differs from the GST registry.", "Upload the latest certificate or send a name-change proof.")
    ctx.check("gst_trade_registry", "Trade name matches registry",
              name_match(f.get("trade_name", ""), rec["trade_name"]), "Trade name matches the registry record.",
              f"Certificate says '{f.get('trade_name')}', registry says '{rec['trade_name']}'.", d, warn=True)
    sim = address_similarity(f.get("address", ""), rec["principal_place_of_business"])
    ctx.check("gst_address_registry", "Address matches registry", sim >= ADDRESS_THRESHOLD, "Principal place of business matches the registry.",
              "The address on the certificate differs from the registry.", d, warn=True)
    return rec


def _check_udyam(ctx: Ctx, f: dict, declared: dict, gst_rec: dict | None):
    d = "udyam_certificate"
    printed = normalise_udyam(f.get("udyam_number") or "")
    dec = normalise_udyam(declared.get("udyam_number") or "")
    number = printed or dec
    rec = None
    if number:
        ok_fmt = is_valid_udyam(number)
        ctx.check("udyam_format", "Udyam number format", ok_fmt, f"{mask(number, 9, 3)} is well-formed.", f"{mask(number, 9, 3)} is not a valid Udyam number format.", d)
        if ok_fmt:
            rec = registry.lookup_udyam(number)
            if not rec:
                ctx.issue("udyam_not_found", REJECT, d, "This Udyam number is not in the Udyam registry.", "Enter the correct Udyam registration number.")
                ctx.check("udyam_registry", "Found in Udyam registry", False, "", "The number was not found in the registry.", d)
        else:
            ctx.issue("udyam_invalid", REJECT, d, "The Udyam number is not in a valid format.", "Re-enter the Udyam registration number.")
    else:
        ctx.info("udyam_number_absent", "Udyam number", "No number is printed on the certificate; we look the enterprise up by name, city and state.", d)
        cands = registry.find_udyam_candidates(f.get("enterprise_name", ""), f.get("city", ""), f.get("state", ""))
        if len(cands) == 1:
            rec = cands[0]
            ctx.info("udyam_resolved", "Udyam lookup by details", f"Single registry match found ({mask(rec['udyam_number'], 9, 3)}).", d)
        elif len(cands) > 1:
            ctx.check("udyam_registry", "Found in Udyam registry", False, "", f"{len(cands)} registry records share this name and city.", d, warn=True)
            ctx.issue("udyam_ambiguous", REVIEW, d, "More than one Udyam record matches the name and city.", "Enter your Udyam registration number so we can match it exactly.")
        else:
            ctx.check("udyam_registry", "Found in Udyam registry", False, "", "No Udyam registration was found for this enterprise name and city.", d)
            ctx.issue("udyam_not_found", REJECT, d, "We could not find this enterprise in the Udyam registry.", "Enter your Udyam number or upload the correct certificate.")
    if rec:
        ctx.check("udyam_registry", "Found in Udyam registry", True, f"Registered as {rec['enterprise_name']} ({rec['enterprise_type']} enterprise).", "", d)
        ok_n = name_match(f.get("enterprise_name", ""), rec["enterprise_name"])
        ctx.check("udyam_name_registry", "Enterprise name matches registry", ok_n, "Enterprise name matches the registry.",
                  f"Certificate says '{f.get('enterprise_name')}', registry says '{rec['enterprise_name']}'.", d)
        if not ok_n:
            ctx.issue("udyam_name_mismatch", FIX, d, "The enterprise name on the certificate does not match the Udyam registry.", "Upload the correct Udyam certificate.")
        ok_c = norm_name(f.get("city", "")) == norm_name(rec["city"]) if f.get("city") else True
        ctx.check("udyam_city_registry", "City matches registry", ok_c, "City matches.", f"Certificate city '{f.get('city')}' vs registry '{rec['city']}'.", d, warn=True)
        if declared.get("udyam_number") and printed and dec != printed:
            ctx.issue("udyam_declared_mismatch", FIX, d, "The Udyam number you entered differs from the certificate.", "Correct the number.")
    return rec


def _check_id(ctx: Ctx, f: dict, gst_f: dict | None, gst_rec: dict | None, biz_name: str):
    d = "signatory_id"
    vt = parse_date(f.get("valid_till"))
    if vt is None:
        ctx.check("id_validity", "ID is valid", False, "", "Could not read the ID's expiry date.", d, warn=True)
        ctx.issue("id_expiry_unreadable", REVIEW, d, "The expiry date on the ID could not be read.", "Upload a clearer image of the ID.")
    else:
        ok = vt >= ctx.today
        ctx.check("id_validity", "ID is valid", ok, f"Valid until {vt}.", f"The ID expired on {vt}.", d)
        if not ok:
            ctx.issue("id_expired", FIX, d, f"The signatory ID expired on {vt}.", "Upload a current government-issued ID.")
    # signatory authority
    desig = (f.get("designation") or "").lower()
    signer = f.get("name") or ""
    proprietor = ""
    legal = (gst_rec or {}).get("legal_name") or (gst_f or {}).get("legal_name") or ""
    owner, _trade = strip_proprietor(legal)
    proprietor = owner
    is_prop = bool(proprietor) and name_match(signer, proprietor, 90)
    if is_prop:
        ctx.check("signatory_authority", "Signatory is authorised", True, f"{signer} is the proprietor named on the GST registration.", "", d)
    elif desig in AUTHORISED_DESIGNATIONS:
        ctx.check("signatory_authority", "Signatory is authorised", True, f"Designation '{f.get('designation')}' can sign for the business.", "", d)
    else:
        ctx.check("signatory_authority", "Signatory is authorised", False, "",
                  f"'{f.get('designation')}' is not an owner/partner/director and is not the proprietor on record.", d, warn=True)
        ctx.issue("signatory_authority", REVIEW, d, f"{signer} ({f.get('designation')}) is not listed as an owner or partner.", "Upload an authorisation letter signed by the owner.")
    if proprietor and not is_prop and norm_name(proprietor) != "":
        ctx.check("signatory_vs_proprietor", "Signatory matches proprietor", False, "",
                  f"GST registration is in the name of {proprietor}, but the ID is for {signer}.", d, warn=True)


def _check_address_proof(ctx: Ctx, f: dict):
    d = "address_proof"
    bd = parse_date(f.get("bill_date"))
    if bd is None:
        ctx.check("bill_date", "Bill is recent", False, "", "The bill date could not be read.", d, warn=True)
        ctx.issue("bill_date_unreadable", REVIEW, d, "The date on the bill could not be read.", "Upload a clearer copy of a recent bill.")
        return
    age = (ctx.today - bd).days
    if age < 0:
        ctx.check("bill_date", "Bill is recent", False, "", f"The bill is dated {bd}, which is in the future.", d)
        ctx.issue("bill_future_dated", FIX, d, "The bill date is in the future.", "Upload a genuine, current bill.")
    else:
        ok = age <= ADDRESS_PROOF_MAX_AGE_DAYS
        ctx.check("bill_date", "Bill is recent", ok, f"Bill is {age} days old (limit {ADDRESS_PROOF_MAX_AGE_DAYS}).",
                  f"The bill is {age} days old; address proof must be no older than {ADDRESS_PROOF_MAX_AGE_DAYS} days.", d)
        if not ok:
            ctx.issue("address_proof_stale", FIX, d, f"The utility bill is {age} days old (limit {ADDRESS_PROOF_MAX_AGE_DAYS}).", "Upload a bill dated within the last 90 days.")


# ---------------------------------------------------------------- cross-document checks

def _cross_checks(ctx: Ctx, docs: dict[str, dict], gst_rec: dict | None, udy_rec: dict | None):
    names: dict[str, str] = {}
    g = docs.get("gst_certificate")
    if g:
        names["GST trade name"] = g.get("trade_name") or ""
    if udy_rec or docs.get("udyam_certificate"):
        names["Udyam enterprise name"] = (docs.get("udyam_certificate") or {}).get("enterprise_name") or ""
    if docs.get("signatory_id"):
        names["ID 'for business'"] = docs["signatory_id"].get("business") or ""
    if docs.get("address_proof"):
        names["Bill 'billed to'"] = docs["address_proof"].get("billed_to") or ""
    names = {k: v for k, v in names.items() if v}
    if len(names) >= 2:
        ref_k, ref = next(iter(names.items()))
        bad = [(k, v) for k, v in names.items() if not name_match(v, ref, NAME_THRESHOLD)]
        # same trade name but different legal suffix (e.g. Pvt Ltd vs LLP) is a different registration
        ctx.check("name_consistency", "Business name is consistent across documents", not bad,
                  "The business name agrees across all uploaded documents.",
                  "; ".join(f"{k}: '{v}' vs {ref_k}: '{ref}'" for k, v in bad), None)
        if bad:
            ctx.issue("name_mismatch", FIX, None, "The business name differs between documents: " + ", ".join(k for k, _ in bad) + ".",
                      "Upload documents that all carry the same business name, or send proof of a name change.")
    # addresses
    addr_src = {}
    if gst_rec:
        addr_src["GST registry"] = gst_rec["principal_place_of_business"]
    elif g and g.get("address"):
        addr_src["GST certificate"] = g["address"]
    if docs.get("address_proof") and docs["address_proof"].get("address"):
        addr_src["Utility bill"] = docs["address_proof"]["address"]
    if len(addr_src) >= 2:
        (k1, a1), (k2, a2) = list(addr_src.items())[:2]
        sim = address_similarity(a1, a2)
        pin_ok = pincode(a1) == pincode(a2) or not (pincode(a1) and pincode(a2))
        ok = sim >= ADDRESS_THRESHOLD and pin_ok
        ctx.check("address_match", "Address on bill matches GST address", ok,
                  f"{k2} address agrees with the {k1} (similarity {sim:.0f}%).",
                  f"{k2} address does not match the {k1} (similarity {sim:.0f}%).", None)
        if not ok:
            ctx.issue("address_mismatch", FIX, "address_proof", "The address on the utility bill does not match the registered business address.",
                      "Upload a bill for the registered business address, or update your GST address.")
    # registry cross: GST state vs Udyam state
    if gst_rec and udy_rec:
        same_state = norm_name(gst_rec["state"]) == norm_name(udy_rec["state"])
        ctx.check("state_consistency", "GST and Udyam are in the same state", same_state, f"Both are registered in {gst_rec['state']}.",
                  f"GST is in {gst_rec['state']} but Udyam is in {udy_rec['state']}.", None, warn=True)


# ---------------------------------------------------------------- entry point

def verify(extracted: dict[str, dict], qualities: dict[str, dict], notes: dict[str, list], detected: dict[str, str],
           declared: dict, today: date) -> dict:
    """extracted: {doc_type: fields}. Returns the full verification report."""
    ctx = Ctx(today=today)
    required = required_documents(declared)
    clean: dict[str, dict] = {}
    readable: dict[str, bool] = {}

    for doc in DOC_TYPES:
        if doc not in extracted:
            continue
        det = detected.get(doc, doc)
        if det not in ("unknown", doc):
            ctx.check("doc_type", "Correct document type", False, "", f"This looks like a {DOC_LABELS.get(det, det)}, not a {DOC_LABELS[doc]}.", doc)
            ctx.issue("wrong_document_type", FIX, doc, f"The file uploaded as {DOC_LABELS[doc]} looks like a {DOC_LABELS.get(det, det)}.",
                      f"Upload your {DOC_LABELS[doc]} here.")
            readable[doc] = False
            continue
        readable[doc] = _quality(ctx, doc, qualities.get(doc, {}), extracted[doc], notes.get(doc, []))
        if readable[doc]:
            clean[doc] = extracted[doc]

    for doc in required:
        if doc not in extracted:
            ctx.check(f"missing_{doc}", f"{DOC_LABELS[doc]} provided", False, "", "This document has not been uploaded.", doc)
            ctx.issue("missing_document", FIX, doc, f"The {DOC_LABELS[doc]} is missing.", f"Upload your {DOC_LABELS[doc]}.")

    gst_rec = udy_rec = None
    if "gst_certificate" in clean:
        gst_rec = _check_gst(ctx, clean["gst_certificate"], declared)
    elif declared.get("gstin") and "gst_certificate" not in extracted:
        pass
    if "udyam_certificate" in clean:
        udy_rec = _check_udyam(ctx, clean["udyam_certificate"], declared, gst_rec)
    if "signatory_id" in clean:
        _check_id(ctx, clean["signatory_id"], clean.get("gst_certificate"), gst_rec, "")
    if "address_proof" in clean:
        _check_address_proof(ctx, clean["address_proof"])
    _cross_checks(ctx, clean, gst_rec, udy_rec)

    severities = {i.severity for i in ctx.issues}
    only_missing = ctx.issues and all(i.code == "missing_document" for i in ctx.issues)
    if REJECT in severities:
        status = "rejected"
    elif only_missing:
        status = "incomplete"
    elif FIX in severities:
        status = "action_required"
    elif REVIEW in severities:
        status = "needs_review"
    else:
        status = "verified"

    summary = {
        "verified": "All documents are valid and consistent with the GST and Udyam registries.",
        "needs_review": "Documents look genuine but a few details need a quick manual review by our team.",
        "action_required": "We found problems you can fix by re-uploading or correcting documents.",
        "incomplete": "Some required documents are still missing.",
        "rejected": "A registration could not be verified, so we cannot proceed with this identity as submitted.",
    }[status]

    doc_status = {}
    for doc in DOC_TYPES:
        if doc not in extracted:
            doc_status[doc] = "missing" if doc in required else "not_required"
            continue
        dc = [c for c in ctx.checks if c.doc == doc]
        di = [i for i in ctx.issues if i.doc == doc]
        if any(i.severity == REJECT for i in di):
            doc_status[doc] = "failed"
        elif any(i.severity == FIX for i in di):
            doc_status[doc] = "failed"
        elif di or any(c.status == "warn" for c in dc):
            doc_status[doc] = "review"
        else:
            doc_status[doc] = "ok"
    # address / name issues recorded against no doc make every readable doc "review"
    return {
        "status": status,
        "summary": summary,
        "required_documents": required,
        "document_status": doc_status,
        "checks": [c.as_dict() for c in ctx.checks],
        "issues": [i.as_dict() for i in ctx.issues],
        "next_actions": list(dict.fromkeys(i.action for i in ctx.issues)),
        "registry": {
            "gstin": ({"found": True, "status": gst_rec["status"], "trade_name": gst_rec["trade_name"], "constitution": gst_rec["constitution"],
                       "state": gst_rec["state"], "gstin": mask(gst_rec["gstin"])} if gst_rec else {"found": False}),
            "udyam": ({"found": True, "enterprise_name": udy_rec["enterprise_name"], "type": udy_rec["enterprise_type"],
                       "udyam_number": mask(udy_rec["udyam_number"], 9, 3)} if udy_rec else {"found": False}),
        },
        "checked_on": today.isoformat(),
    }
