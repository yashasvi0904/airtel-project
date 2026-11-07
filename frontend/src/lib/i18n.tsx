"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, journeyStore } from "./api";
import { setFormatLocale } from "./format";
import { DEFAULT_LANG, detectLang, isLang, localeOf, type Lang } from "./languages";
import { localizeMessage } from "./localizeMessage";

/**
 * Translation layer. Source strings are the English text itself: `tr("Pay {amount}", { amount })`.
 * A missing translation falls back to English, never to a blank or a key. Locale files live in ./locales/<code>.json and are
 * produced by scripts/translate_locales.py (machine translation + placeholder checks; `hi` also carries hand-written copy).
 * Locale files are loaded on demand so a Tamil user does not download nine other languages.
 */
type Messages = Record<string, string>;
type Vars = Record<string, string | number>;

const loaders: Record<Exclude<Lang, "en">, () => Promise<{ default: Messages }>> = {
  hi: () => import("./locales/hi.json"), mr: () => import("./locales/mr.json"), kn: () => import("./locales/kn.json"), gu: () => import("./locales/gu.json"),
  te: () => import("./locales/te.json"), ta: () => import("./locales/ta.json"), bn: () => import("./locales/bn.json"), pa: () => import("./locales/pa.json"),
  ml: () => import("./locales/ml.json"),
};
const cache = new Map<Lang, Messages>();

const fill = (text: string, vars?: Vars) => (vars ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : text);

interface LangState { lang: Lang; setLang: (l: Lang) => void; tr: (text: string, vars?: Vars) => string; t: (text: string, vars?: Vars) => string; lm: (serverMessage: string) => string; tn: (text: string, vars?: Vars) => string; ready: boolean }
const Ctx = createContext<LangState>({ lang: DEFAULT_LANG, setLang: () => {}, tr: fill, t: fill, lm: (m) => m, tn: fill, ready: true });
const STORE = "udyam.lang";

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(DEFAULT_LANG);
  const [msgs, setMsgs] = useState<Messages>({});
  const [ready, setReady] = useState(false);

  const load = useCallback(async (l: Lang) => {
    if (l === "en") return {};
    const hit = cache.get(l);
    if (hit) return hit;
    try {
      const m = (await loaders[l]()).default;
      cache.set(l, m);
      return m;
    } catch {
      return {}; // offline / chunk failed: stay readable in English rather than break the page
    }
  }, []);

  const apply = useCallback(async (l: Lang) => {
    const m = await load(l);
    setMsgs(m);
    setLangState(l);
    setFormatLocale(localeOf(l));
    document.documentElement.lang = l;
    setReady(true);
  }, [load]);

  // first visit: the phone's own language list decides; afterwards the customer's choice wins
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(STORE); } catch { /* private mode */ }
    void apply(isLang(saved) ? saved : detectLang(navigator.languages?.length ? navigator.languages : [navigator.language]));
  }, [apply]);

  const setLang = useCallback((l: Lang) => {
    try { localStorage.setItem(STORE, l); } catch { /* ignore */ }
    void apply(l);
    const jid = journeyStore.get(); // keep the server-side journey (and so the advisor) in the customer's language
    if (jid) api(`/journeys/${jid}/language`, { method: "PUT", body: { language: l } }).catch(() => {});
  }, [apply]);

  const tr = useCallback((text: string, vars?: Vars) => fill(lang === "en" ? text : msgs[text] ?? text, vars), [lang, msgs]);
  const lm = useCallback((m: string) => localizeMessage(m, tr), [tr]);
  // identity never changes, yet always uses the current language: for data-loading callbacks that must not re-run on a language switch
  const latest = useRef(tr);
  useEffect(() => { latest.current = tr; }, [tr]);
  const tn = useCallback((text: string, vars?: Vars) => latest.current(text, vars), []);
  const value = useMemo(() => ({ lang, setLang, tr, t: tr, lm, tn, ready }), [lang, setLang, tr, lm, tn, ready]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);

export { tx } from "./tx";
