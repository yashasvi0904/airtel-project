"""Format / checksum validators and OCR-repair helpers for Indian business identifiers."""
import itertools
import re
from datetime import date, datetime

CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^(0[1-9]|[12]\d|3[0-8])[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")

# characters OCR commonly confuses
TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "T": "7"}
TO_ALPHA = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G", "7": "T", "4": "A"}
ALNUM_ALTS = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2", "6": "G", "G": "6"}


def gstin_checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        val = CHARSET.index(ch) * (1 if i % 2 == 0 else 2)
        total += val // 36 + val % 36
    return CHARSET[(36 - total % 36) % 36]


def is_valid_gstin(gstin: str, check_sum: bool = True) -> bool:
    g = (gstin or "").strip().upper()
    if not GSTIN_RE.match(g):
        return False
    return gstin_checksum_char(g[:14]) == g[14] if check_sum else True


def gstin_format_ok(gstin: str) -> bool:
    return bool(GSTIN_RE.match((gstin or "").strip().upper()))


def _positional_fix(s: str) -> str:
    """Coerce each character to the class its position requires (digit/letter/alnum)."""
    out = []
    for i, ch in enumerate(s):
        if i in (0, 1, 7, 8, 9, 10):
            out.append(TO_DIGIT.get(ch, ch) if not ch.isdigit() else ch)
        elif i in (2, 3, 4, 5, 6, 11):
            out.append(TO_ALPHA.get(ch, ch) if ch.isdigit() else ch)
        elif i == 13:
            out.append("Z")
        else:
            out.append(ch)
    return "".join(out)


def repair_gstin(raw: str) -> tuple[str, bool]:
    """Return (best_gstin, was_corrected). Prefers a checksum-valid candidate reachable by OCR-confusion swaps."""
    s = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    if len(s) != 15:
        return s, False
    if is_valid_gstin(s):
        return s, False
    fixed = _positional_fix(s)
    if is_valid_gstin(fixed):
        return fixed, fixed != s
    # try swapping up to two confusable characters
    idx = [i for i, ch in enumerate(fixed) if ch in ALNUM_ALTS and i not in (13,)]
    for n in (1, 2):
        for combo in itertools.combinations(idx, n):
            cand = list(fixed)
            for i in combo:
                cand[i] = ALNUM_ALTS[cand[i]]
            c = "".join(cand)
            if is_valid_gstin(c):
                return c, True
    return fixed, fixed != s


def find_gstin_candidates(text: str) -> list[str]:
    """Find 15-character GSTIN-looking tokens in OCR text."""
    toks = re.findall(r"[A-Za-z0-9]{15}", re.sub(r"[\s\-]", "", text or ""))
    return toks


def normalise_udyam(raw: str) -> str:
    s = re.sub(r"\s+", "", (raw or "").upper()).replace("–", "-").replace("—", "-")
    s = re.sub(r"[^A-Z0-9\-]", "", s)
    m = re.match(r"^UDYAM-?([A-Z]{2})-?(\d{2})-?(\d{7})$", s)
    return f"UDYAM-{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else s


def is_valid_udyam(u: str) -> bool:
    return bool(UDYAM_RE.match(normalise_udyam(u)))


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip().replace("O", "0").replace("o", "0")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None
