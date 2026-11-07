"""Build the translation source list.

Collects every customer-visible English string:
  * frontend:  tr("...") and tx("...") literals under frontend/src (admin excluded)
  * backend:   user-facing sentences in the Python source (f-strings become templates with {p1}, {p2} placeholders), found by AST
  * dataset:   catalogue descriptions / categories / units, business types, segments, internet options
  * fixed:     status words, actors, tracker labels

Writes frontend/src/lib/locales/_source.json (strings to translate) and _patterns.json (regexes the browser uses to match a
server sentence that embeds values, e.g. "Needs at least 5 employees (you have 3)." -> translated template + captured values).

Run:  backend/.venv/Scripts/python scripts/extract_strings.py
"""
import ast
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
OUT = FE / "lib" / "locales"
BE = ROOT / "backend" / "app"
DATA = ROOT / "assignment" / "data"

# ------------------------------------------------------------------ frontend literals
TR = re.compile(r'\bt[rxn]\(\s*"((?:[^"\\]|\\.)*)"')


def frontend_strings() -> set[str]:
    out = set()
    for f in FE.rglob("*.ts*"):
        rel = f.relative_to(FE).as_posix()
        if rel.startswith(("app/admin/", "lib/locales/")):
            continue
        for m in TR.finditer(f.read_text(encoding="utf-8")):
            try:
                out.add(json.loads('"' + m.group(1) + '"'))
            except ValueError:
                out.add(m.group(1))
    return out


# ------------------------------------------------------------------ backend sentences (AST)
MODULES = ["services/eligibility.py", "services/recommender.py", "services/pricing.py", "services/profile.py", "services/orders.py", "services/catalogue.py",
           "services/kyc", "services/payments/service.py", "services/payments/sandbox.py", "services/payments/base.py", "services/payments/razorpay.py",
           "routers", "security.py"]
SKIP_CALLS = {"info", "warning", "error", "debug", "exception", "getLogger", "print", "Field", "mapped_column", "relationship", "ForeignKey", "String", "UniqueConstraint"}
SENTENCE = re.compile(r"^[A-Z][^{}]*[ ][^{}]*[.!?)\w]$|^[A-Z].*\{p\d+\}.*$|^\{p\d+\}[% ].*[A-Za-z]{4,}.*$")


def _template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts, n = [], 0
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            else:
                n += 1
                parts.append("{p%d}" % n)
        return "".join(parts)
    return None


def _callname(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def backend_strings() -> set[str]:
    out = set()
    files: list[Path] = []
    for m in MODULES:
        p = BE / m
        files += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        skip: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callname(node) in SKIP_CALLS:
                skip |= {id(n) for n in ast.walk(node)}
            if isinstance(node, ast.JoinedStr):  # the literal pieces inside an f-string are not sentences on their own
                skip |= {id(v) for v in node.values}
            # docstrings
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body and isinstance(node.body[0], ast.Expr):
                skip.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if id(node) in skip or not isinstance(node, (ast.Constant, ast.JoinedStr)):
                continue
            t = _template(node)
            t = t.strip() if t else t  # pieces are often joined with a leading space
            if not t or len(t) < 12 or " " not in t or not re.match(r"[A-Z]|\{p\d+\}[% ]", t):
                continue
            if "\n" in t or t.startswith(("SELECT", "Bearer", "http")) or re.search(r"\bapp\.|\.py\b|%s|\bsqlalchemy\b", t):
                continue
            if SENTENCE.match(t.strip()):
                out.add(t.strip())
    return out


# ------------------------------------------------------------------ dataset-driven + fixed words
def dataset_strings() -> set[str]:
    out = set()
    with open(DATA / "product_catalogue.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out |= {r["category"], r["description"], r["unit"]}
    with open(DATA / "smb_leads.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out |= {r["business_type"] for r in rows} | {r["segment"] for r in rows} | {r["current_internet"] for r in rows}
    rules = json.loads((BE / "data" / "pricing_rules.json").read_text(encoding="utf-8"))

    def labels(node):
        if isinstance(node, dict):
            if isinstance(node.get("label"), str):
                yield node["label"]
            for v in node.values():
                yield from labels(v)
        elif isinstance(node, list):
            for v in node:
                yield from labels(v)

    out |= set(labels(rules))  # discount labels such as "12-month commitment"
    return {s for s in out if s}


FIXED = [
    # order / payment / kyc / attempt statuses, event names
    "Placed", "Kyc Verified", "Install Scheduled", "Installing", "Activated", "Cancelled", "Pending", "Processing", "Paid", "Failed", "Expired", "Succeeded", "Created",
    "Not Started", "Awaiting Documents", "Incomplete", "Action Required", "Needs Review", "Rejected", "Verified", "Approved",
    "Payment Started", "Payment Paid", "Payment Failed", "Payment Expired", "Payment Cancelled", "Payment Duplicate", "Payment Alert", "Kyc Incomplete",
    "customer", "system", "admin", "Payment", "Order placed", "KYC verification", "Installation scheduled", "Installation in progress", "Activated",
    "9:00 - 13:00", "14:00 - 18:00", "Mobile hotspot", "UPI", "Card", "Net banking",
]


def python_tr_strings() -> set[str]:
    """Strings the backend translates with i18n.tr("...") plus the advisor chips and need labels (also sent to the browser)."""
    out: set[str] = set()
    for f in BE.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("tr", "tx") and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n":
                if node.args:
                    arg = node.args[0]
                    for c in ([arg.body, arg.orelse] if isinstance(arg, ast.IfExp) else [arg]):  # "more" if d > 0 else "less"
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            out.add(c.value)
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.advisor import templates as T  # noqa: E402
    from app.services.recommender import NEED_LABEL  # noqa: E402

    for chips in T.CHIPS["en"].values():
        out |= set(chips)
    out |= set(NEED_LABEL.values()) | {"Make it cheaper", "Add CCTV", "Why do I need failover?", "Show my recommendation", "Broadband"}
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fe, be, ds = frontend_strings(), backend_strings(), dataset_strings()
    py = python_tr_strings()
    allstr = sorted(fe | be | ds | py | set(FIXED), key=lambda s: (s.lower(), s))
    (OUT / "_source.json").write_text(json.dumps(allstr, ensure_ascii=False, indent=1), encoding="utf-8")

    # regexes for backend templates that embed values (browser-side matching)
    pats = []
    for t in sorted(be):
        if "{p" not in t:
            continue
        names = re.findall(r"\{(p\d+)\}", t)
        rx = re.escape(t)
        for n in names:
            rx = rx.replace(re.escape("{" + n + "}"), "(.+?)")
        pats.append({"re": "^" + rx + "$", "tpl": t, "names": names})
    # longest, most specific first
    pats.sort(key=lambda p: -len(p["re"]))
    (OUT / "_patterns.json").write_text(json.dumps(pats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"frontend {len(fe)} | backend {len(be)} ({len(pats)} templates) | dataset {len(ds)} | python tr {len(py)} | fixed {len(FIXED)} | total unique {len(allstr)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
