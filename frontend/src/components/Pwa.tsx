"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";

/** Chrome/Edge/Android fire this when the site is installable; Safari (iOS) never does. */
interface InstallEvent extends Event { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> }

interface PwaState {
  /** True when we can offer an install: a native prompt is available, or it is iOS Safari (manual steps). */
  canInstall: boolean;
  isIOS: boolean;
  installed: boolean;
  /** Triggers the native prompt; on iOS returns "ios" so the caller can show the manual steps. */
  install: () => Promise<"accepted" | "dismissed" | "ios" | "unavailable">;
}

const Ctx = createContext<PwaState>({ canInstall: false, isIOS: false, installed: false, install: async () => "unavailable" });
export const usePwa = () => useContext(Ctx);

const DISMISS_KEY = "udyam.installBanner.dismissedAt";
const DISMISS_DAYS = 7;

const isStandalone = () =>
  typeof window !== "undefined" && (window.matchMedia("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone === true);

export function PwaProvider({ children }: { children: React.ReactNode }) {
  const [evt, setEvt] = useState<InstallEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    setInstalled(isStandalone());
    const ua = navigator.userAgent;
    // iPadOS reports itself as a Mac with touch points.
    setIsIOS(/iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1));

    // The service worker gives offline fallback + faster repeat opens. Production builds only: in `next dev` it would serve stale code.
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => { /* optional enhancement */ });
    }

    const onPrompt = (e: Event) => { e.preventDefault(); setEvt(e as InstallEvent); };
    const onInstalled = () => { setInstalled(true); setEvt(null); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);

  const install = useCallback(async () => {
    if (evt) {
      await evt.prompt();
      const { outcome } = await evt.userChoice;
      setEvt(null);
      return outcome;
    }
    return isIOS ? "ios" as const : "unavailable" as const;
  }, [evt, isIOS]);

  const value = useMemo<PwaState>(() => ({ canInstall: !installed && (!!evt || isIOS), isIOS, installed, install }), [evt, installed, isIOS, install]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** "Install app" entry for menus. On iOS it reveals the manual Share -> Add to Home Screen steps. */
export function InstallButton({ className, onDone }: { className?: string; onDone?: () => void }) {
  const { tr } = useLang();
  const { canInstall, install } = usePwa();
  const [help, setHelp] = useState(false);
  if (!canInstall) return null;
  return (
    <>
      <button className={className} onClick={async () => { const r = await install(); if (r === "ios") setHelp(true); else onDone?.(); }}>{tr("Install app")}</button>
      {help && <p role="status" className="px-3 text-xs text-muted">{tr("On iPhone: tap the Share button, then “Add to Home Screen”.")}</p>}
    </>
  );
}

/** Dismissible card on the home page. Not sticky, so it never covers the sticky price / checkout bars. */
export function InstallBanner() {
  const { tr } = useLang();
  const path = usePathname();
  const { canInstall, isIOS, install } = usePwa();
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    try {
      const at = Number(localStorage.getItem(DISMISS_KEY) || 0);
      setHidden(!!at && Date.now() - at < DISMISS_DAYS * 864e5);
    } catch { setHidden(false); }
  }, []);

  if (path !== "/" || !canInstall || hidden) return null;
  const dismiss = () => { setHidden(true); try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* private mode */ } };
  return (
    <section aria-label={tr("Install the app")} className="mx-auto mt-3 flex w-[calc(100%-2rem)] max-w-5xl items-center gap-3 rounded-xl border border-line bg-brand-soft p-3">
      <span aria-hidden className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand text-2xl font-bold leading-none text-white">a</span>
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold">{tr("Install the app")}</p>
        <p className="text-xs text-muted">{isIOS ? tr("On iPhone: tap the Share button, then “Add to Home Screen”.") : tr("Opens full-screen from your home screen. Voice and camera work as usual.")}</p>
      </div>
      {!isIOS && <button onClick={async () => { if ((await install()) === "accepted") dismiss(); }} className="min-h-11 shrink-0 rounded-lg bg-brand px-4 text-sm font-semibold text-white">{tr("Install")}</button>}
      <button onClick={dismiss} aria-label={tr("Not now")} className="grid min-h-11 min-w-11 shrink-0 place-items-center rounded-lg text-lg text-muted hover:bg-white">×</button>
    </section>
  );
}
