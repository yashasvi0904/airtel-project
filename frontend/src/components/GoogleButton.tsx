"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface GoogleId {
  initialize: (o: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: string }) => void;
  renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
}
declare global {
  interface Window { google?: { accounts: { id: GoogleId } } }
}

const SRC = "https://accounts.google.com/gsi/client";

function loadScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SRC}"]`);
    const s = existing ?? Object.assign(document.createElement("script"), { src: SRC, async: true, defer: true });
    s.addEventListener("load", () => resolve());
    s.addEventListener("error", () => reject(new Error("Could not load Google sign-in")));
    if (!existing) document.head.appendChild(s);
  });
}

/** "Sign in with Google" / "Sign up with Google" using Google Identity Services. The client ID comes from the backend. */
export default function GoogleButton({ mode, onCredential, onError }: { mode: "login" | "register"; onCredential: (c: string) => void; onError: (m: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "disabled">("loading");
  const cb = useRef(onCredential);
  useEffect(() => { cb.current = onCredential; });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api<{ google_client_id: string | null }>("/auth/config");
        if (!cfg.google_client_id) return !cancelled && setState("disabled");
        await loadScript();
        if (cancelled || !box.current || !window.google) return;
        window.google.accounts.id.initialize({ client_id: cfg.google_client_id, callback: (r) => cb.current(r.credential) });
        const width = Math.min(380, Math.max(220, box.current.offsetWidth));
        window.google.accounts.id.renderButton(box.current, { type: "standard", theme: "outline", size: "large", text: mode === "login" ? "signin_with" : "signup_with", shape: "rectangular", width, logo_alignment: "left" });
        setState("ready");
      } catch {
        if (!cancelled) {
          setState("disabled");
          onError("Google sign-in could not be loaded. You can still use email and password.");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [mode, onError]);

  if (state === "disabled") {
    return (
      <button type="button" disabled title="Google sign-in is not configured on this server (set GOOGLE_CLIENT_ID)" className="flex min-h-11 w-full cursor-not-allowed items-center justify-center gap-2 rounded-lg border border-line bg-neutral-50 px-4 text-sm font-medium text-neutral-400">
        <GoogleG /> {mode === "login" ? "Sign in with Google" : "Sign up with Google"} (not configured)
      </button>
    );
  }
  return <div ref={box} className="flex min-h-11 w-full justify-center" aria-label={mode === "login" ? "Sign in with Google" : "Sign up with Google"} />;
}

function GoogleG() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z" />
      <path fill="#FBBC05" d="M10.5 28.7c-.5-1.5-.8-3.1-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}
