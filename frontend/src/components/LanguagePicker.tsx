"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLang } from "@/lib/i18n";
import { LANGS } from "@/lib/languages";
import { cx } from "@/components/ui";

/** Globe button + bottom sheet listing the ten languages by their own names (usable one-handed on a phone). */
export default function LanguagePicker({ className }: { className?: string }) {
  const { lang, setLang, tr } = useLang();
  const [open, setOpen] = useState(false);
  const activeRef = useRef<HTMLButtonElement>(null);
  const current = LANGS.find((l) => l.code === lang);

  useEffect(() => {
    if (!open) return;
    activeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden"; // the page behind must not scroll under the sheet
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open]);

  return (
    <>
      <button onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label={tr("Choose language")}
        className={cx("inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-line px-3 text-sm font-semibold hover:bg-neutral-100", className)}>
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z" /></svg>
        <span lang={lang}>{current?.native}</span>
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={() => setOpen(false)}>
          <div role="dialog" aria-modal="true" aria-label={tr("Choose language")} onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-t-2xl bg-white p-4 pb-6 shadow-xl sm:rounded-2xl">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-base font-bold">{tr("Choose your language")}</p>
              <button onClick={() => setOpen(false)} aria-label={tr("Close")} className="grid h-11 w-11 place-items-center rounded-lg text-xl hover:bg-neutral-100">×</button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {LANGS.map((l) => (
                <button key={l.code} ref={l.code === lang ? activeRef : undefined} lang={l.code} aria-pressed={l.code === lang}
                  onClick={() => { setLang(l.code); setOpen(false); }}
                  className={cx("min-h-12 rounded-lg border px-3 text-left text-base", l.code === lang ? "border-brand bg-brand-soft font-semibold text-brand" : "border-line hover:border-brand")}>
                  {l.native}
                  <span className="block text-[11px] font-normal text-muted">{l.english}</span>
                </button>
              ))}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

/** Always-visible language row for the first screen: a first-time visitor should never have to hunt for their language. */
export function LanguageChips() {
  const { lang, setLang, tr } = useLang();
  return (
    <div className="mb-4" role="group" aria-label={tr("Choose your language")}>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {LANGS.map((l) => (
          <button key={l.code} lang={l.code} aria-pressed={l.code === lang} onClick={() => setLang(l.code)}
            className={cx("min-h-11 shrink-0 rounded-full border px-4 text-sm font-medium", l.code === lang ? "border-white bg-white text-ink" : "border-white/40 text-white hover:bg-white/10")}>
            {l.native}
          </button>
        ))}
      </div>
    </div>
  );
}
