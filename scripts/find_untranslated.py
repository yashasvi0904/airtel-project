"""List human-readable English that is not wrapped in tr(...) in the customer-facing frontend code.

Heuristic, tuned to this codebase: finds (1) string literals that look like sentences, (2) JSX lines that are plain text,
(3) template literals with words. Admin pages are intentionally excluded (back-office is English).
Usage: python scripts/find_untranslated.py [--quiet]   (exit code 1 if anything is found)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
EXCLUDE = ("app/admin/", "lib/locales/", "lib/api.ts", "lib/types.ts", "lib/languages.ts", "lib/speech.ts", "lib/i18n.tsx", "lib/format.ts")
CODEY = re.compile(r"^(use |https?:|/|#|[a-z]+[A-Z]|[a-z_]+\.|[\w-]+$|\w+:\w)")
SENTENCE = re.compile(r'"([A-Z][A-Za-z\'’]+(?: [A-Za-z0-9\'’&(),./:%-]+){1,}[.!?:]?)"')
CODE_WORDS = {"finally", "else", "catch", "try", "checks", "enterprise", "return", "months"}
MIXED = re.compile(r">\s*([A-Za-z][A-Za-z' ,.:&;/()-]{3,}?)\s*\{|\}\s*([A-Za-z][A-Za-z' ,.:&;/()-]{3,}?)\s*<|\}\s+([a-z][a-z ]{3,})\s*\{")
TAILWIND = re.compile(r"\b(flex|grid|px-|py-|text-|bg-|border|rounded|gap-|mt-|mb-|min-h|max-w|font-|hover:|sm:|md:|lg:)")


def findings():
    for f in sorted(ROOT.rglob("*.ts*")):
        rel = f.relative_to(ROOT).as_posix()
        if any(rel.startswith(e) or rel == e for e in EXCLUDE):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            s = line.strip()
            if not s or s.startswith(("//", "import ", "*", "/*", "export type", "interface ", "type ")):
                continue
            stripped = re.sub(r't[rxn]\((?:"[^"]*"|`[^`]*`)[^)]*\)', "", line)  # ignore what is already wrapped
            for m in SENTENCE.finditer(stripped):
                txt = m.group(1)
                if TAILWIND.search(txt) or CODEY.match(txt) or "className" in stripped[max(0, m.start() - 12):m.start()]:
                    continue
                yield rel, n, txt
            for m in MIXED.finditer(stripped):
                txt = next(g for g in m.groups() if g)
                if txt.strip() not in CODE_WORDS and not re.search(r"\($|\)$|^as |^docs", txt.strip()) and re.search(r"[A-Za-z]{4,}", txt) and not re.match(r"^(px|py|mt|mb|rounded|text|bg|flex|grid|border|font|min|max|gap|space)\b", txt.strip()):
                    yield rel, n, "(mixed) " + txt.strip()
            # plain-text JSX line (no tags/braces/operators), at least two words
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,.'’&:!?()/-]{6,}", s) and " " in s and not re.match(r"(return|const|let|if|else|case|default|await|throw)\b", s):
                yield rel, n, s


if __name__ == "__main__":
    items = list(findings())
    if "--quiet" not in sys.argv:
        for rel, n, txt in items:
            print(f"{rel}:{n}: {txt[:100]}")
    print(f"{len(items)} unwrapped string(s)")
    sys.exit(1 if items else 0)
