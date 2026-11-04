"""Turn OCR lines into labelled fields for the four KYC document types."""
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .matching import norm_name
from .ocr import Line, OcrResult, ocr_crop
from .validators import find_gstin_candidates, normalise_udyam, parse_date, repair_gstin

DOC_TYPES = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
DOC_LABELS = {
    "gst_certificate": "GST registration certificate",
    "udyam_certificate": "Udyam registration certificate",
    "signatory_id": "Authorised signatory ID",
    "address_proof": "Address proof (utility bill)",
}

LABELS: dict[str, dict[str, str]] = {
    "gst_certificate": {
        "gstin": "GSTIN", "legal_name": "Legal name", "trade_name": "Trade name", "constitution": "Constitution",
        "address": "Address of principal", "address_cont": "place of business",
        "registration_date": "Date of liability", "registration_type": "Type of registration",
    },
    "udyam_certificate": {
        "udyam_number": "Udyam reg. number", "enterprise_name": "Enterprise name", "major_activity": "Major activity",
        "city": "City", "state": "State", "registration_date": "Date of registration",
    },
    "signatory_id": {
        "name": "Name", "designation": "Designation", "business": "For business", "id_number": "ID no.", "valid_till": "Valid till",
    },
    "address_proof": {
        "consumer_no": "Consumer no.", "billed_to": "Billed to", "address": "Supply address", "bill_date": "Bill date",
        "units": "Units consumed", "amount": "Amount due (INR)",
    },
}
TITLE_HINTS = {
    "gst_certificate": "gstregistrationcertificate",
    "udyam_certificate": "udyamregistrationcertificate",
    "signatory_id": "authorisedsignatoryid",
    "address_proof": "electricitybill",
}
WATERMARK = "SYNTHETICSPECIMENNOTAVALIDDOCUMENT"


@dataclass
class Extracted:
    doc_type: str
    detected_type: str
    fields: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def _is_watermark(text: str) -> bool:
    if sum(c.isdigit() for c in text) >= 2:
        return False  # the watermark has no digits; this is a real value such as a GSTIN
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return False
    t = re.sub(r"[^A-Z]", "", text.upper())
    if len(t) < 2:
        return False
    if len(t) < 5:
        return t in WATERMARK
    return fuzz.partial_ratio(WATERMARK, t) >= 80 and not t.isdigit()


def _match_label(text: str, label: str) -> bool:
    a, b = norm_name(text), norm_name(label)
    return bool(a) and fuzz.ratio(a, b) >= 85


def detect_doc_type(lines: list[Line]) -> str:
    best, best_score = "unknown", 0.0
    title = norm_name(" ".join(l.text for l in lines if l.y0 < 220))
    for dt, labels in LABELS.items():
        hits = sum(any(_match_label(l.text, lab) for l in lines) for lab in labels.values())
        score = hits + (3 if fuzz.partial_ratio(TITLE_HINTS[dt], title) >= 85 else 0)
        if score > best_score:
            best, best_score = dt, score
    return best if best_score >= 4 else "unknown"


def _join_wrapped(parts: list[str]) -> str:
    """Join text that was hard-wrapped at a fixed width, which can split inside a word ('A' + 'ndhra')."""
    out = ""
    for part in (p.strip() for p in parts):
        if not part:
            continue
        if out and (out.endswith((",", "-")) or not part[0].islower()):
            out += " " + part
        else:
            out += part
    return out.strip()


def _pretty(value: str) -> str:
    v = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    v = re.sub(r"\s*&\s*", " & ", v)
    v = re.sub(r"\s*-\s*(?=\d{6}$)", " - ", v)
    return re.sub(r"\s+", " ", v).strip()


def _clean_lines(res: OcrResult) -> list[Line]:
    return [l for l in res.lines if l.text and not _is_watermark(l.text)]


MULTILINE = {("address_proof", "address")}


def _parse_columns(doc_type: str, lines: list[Line], width: float) -> dict[str, tuple[str, float, Line | None]]:
    """Two-column documents: label on the left, value on the same row.
    Labels hidden under the watermark are recovered by position (the value that sits between its neighbours)."""
    labels = LABELS[doc_type]
    left, right = [], []
    for l in lines:
        (left if l.x0 < width * 0.33 else right).append(l)
    found: list[tuple[str, Line]] = []
    for key, lab in labels.items():
        cand = [l for l in left if _match_label(l.text, lab)]
        if cand:
            found.append((key, min(cand, key=lambda l: l.y0)))
    found.sort(key=lambda kv: kv[1].cy)
    out: dict[str, tuple[str, float, Line | None]] = {}
    used: set[int] = set()
    for i, (key, lab) in enumerate(found):
        top = lab.cy - 38
        nxt = found[i + 1][1].cy - 38 if i + 1 < len(found) else lab.cy + 38
        bottom = nxt if (doc_type, key) in MULTILINE else min(nxt, lab.cy + 38)
        vals = sorted((l for l in right if top <= l.cy < bottom and l.x0 > lab.x1), key=lambda l: l.cy)
        used.update(id(v) for v in vals)
        out[key] = (_join_wrapped([v.text for v in vals]), min((v.conf for v in vals), default=0.0), lab)

    # recover labels that the watermark hid: assign the unclaimed value rows lying between neighbouring labels
    keys = list(labels)
    spare = sorted((l for l in right if id(l) not in used), key=lambda l: l.cy)
    for idx, key in enumerate(keys):
        if key in out:
            continue
        prev = next((out[k][2] for k in reversed(keys[:idx]) if k in out), None)
        nxt_l = next((out[k][2] for k in keys[idx + 1:] if k in out), None)
        lo = prev.cy + 25 if prev else 0
        hi = nxt_l.cy - 25 if nxt_l else float("inf")
        vals = [l for l in spare if lo < l.cy < hi]
        if vals:
            out[key] = (_join_wrapped([v.text for v in vals]), min(v.conf for v in vals) * 0.9, None)
            spare = [l for l in spare if l not in vals]
    return out


def _parse_stacked(doc_type: str, lines: list[Line]) -> dict[str, tuple[str, float, Line | None]]:
    """ID card layout: label line followed by its value line, in one column."""
    labels = LABELS[doc_type]
    ordered = sorted(lines, key=lambda l: l.cy)
    out = {}
    all_label_texts = list(labels.values())
    for key, lab in labels.items():
        for i, l in enumerate(ordered):
            if l.x0 > 200 and _match_label(l.text, lab):
                for nxt in ordered[i + 1:]:
                    if abs(nxt.x0 - l.x0) < 30 and nxt.cy > l.cy:
                        if not any(_match_label(nxt.text, x) for x in all_label_texts):
                            out[key] = (nxt.text, nxt.conf, l)
                        break
                break
    return out


def parse_document(claimed_type: str, res: OcrResult) -> Extracted:
    lines = _clean_lines(res)
    width = res.image.shape[1]
    detected = detect_doc_type(lines)
    doc_type = detected if detected != "unknown" else claimed_type
    ext = Extracted(claimed_type, detected)
    if doc_type not in LABELS:
        return ext
    raw = _parse_stacked(doc_type, lines) if doc_type == "signatory_id" else _parse_columns(doc_type, lines, width)

    # second pass: values the full-page OCR missed (monospace GSTIN, blank Udyam number, label hidden by the watermark)
    for key, nxt in (("gstin", "legal_name"), ("udyam_number", "enterprise_name")):
        if doc_type not in ("gst_certificate", "udyam_certificate") or key not in LABELS[doc_type]:
            continue
        if key in raw and raw[key][0].strip():
            continue
        lab = raw[key][2] if key in raw else None
        if lab is not None:
            y0, y1, x0 = lab.cy - 35, lab.cy + 35, max(lab.x1 + 10, width * 0.33)
        else:
            title_bottom = max((l.y1 for l in lines if l.y0 < 200), default=190)
            nxt_lab = raw.get(nxt, ("", 0, None))[2]
            y0, y1 = title_bottom + 5, (nxt_lab.cy - 35 if nxt_lab else title_bottom + 90)
            x0 = width * 0.33
        found = None
        for dx, scale in ((0, 2.5), (-0.03, 2.5), (0, 1.5), (-0.03, 2.0), (0.03, 2.0), (-0.06, 3.0)):
            for l in ocr_crop(res, x0 + dx * width, y0, width - 30, y1, scale=scale):
                if not _is_watermark(l.text) and len(re.sub(r"\W", "", l.text)) >= 8:
                    found = l
                    break
            if found:
                break
        if found:
            raw[key] = (found.text, found.conf, lab)

    fields: dict[str, str | None] = {}
    for key, (text, conf, _lab) in raw.items():
        fields[key] = text.strip() or None
        ext.confidence[key] = round(conf, 2)

    # compose multi-row values and normalise
    if doc_type == "gst_certificate":
        addr = _join_wrapped([x for x in (fields.get("address"), fields.pop("address_cont", None)) if x])
        fields["address"] = _pretty(addr.replace(" ,", ",")) if addr else None
        g = fields.get("gstin")
        if g:
            cands = find_gstin_candidates(g) or [g]
            fixed, corrected = repair_gstin(cands[0])
            fields["gstin"] = fixed
            if corrected:
                ext.notes.append("GSTIN characters were corrected using the checksum (OCR confusion)")
        fields["registration_date"] = _iso(fields.get("registration_date"))
        for k in ("legal_name", "trade_name", "constitution"):
            if fields.get(k):
                fields[k] = _pretty(fields[k])
    elif doc_type == "udyam_certificate":
        if fields.get("udyam_number"):
            fields["udyam_number"] = normalise_udyam(fields["udyam_number"])
        fields["registration_date"] = _iso(fields.get("registration_date"))
        for k in ("enterprise_name", "city", "state", "major_activity"):
            if fields.get(k):
                fields[k] = _pretty(fields[k])
    elif doc_type == "signatory_id":
        fields["valid_till"] = _iso(fields.get("valid_till"))
        for k in ("name", "designation", "business"):
            if fields.get(k):
                fields[k] = _pretty(fields[k])
        if fields.get("designation"):
            fields["designation"] = {"Officeadmin": "Office admin"}.get(fields["designation"].replace(" ", "").capitalize(), fields["designation"])
    elif doc_type == "address_proof":
        addr = fields.get("address")
        fields["address"] = _pretty(addr.replace(" ,", ",")) if addr else None
        fields["bill_date"] = _iso(fields.get("bill_date"))
        if fields.get("billed_to"):
            fields["billed_to"] = _pretty(fields["billed_to"])
    ext.fields = fields
    return ext


def _iso(s: str | None) -> str | None:
    d = parse_date(s)
    return d.isoformat() if d else None
