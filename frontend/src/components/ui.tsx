"use client";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useLang } from "@/lib/i18n";
import { localizeMessage } from "@/lib/localizeMessage";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Button({ variant = "primary", loading, className, children, disabled, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; loading?: boolean }) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-dark disabled:bg-red-300",
    secondary: "bg-white text-ink border border-line hover:bg-neutral-50 disabled:text-neutral-400",
    ghost: "text-brand hover:bg-brand-soft disabled:text-neutral-400",
    danger: "bg-white text-brand border border-brand hover:bg-brand-soft",
  }[variant];
  return (
    <button
      {...p}
      disabled={disabled || loading}
      className={cx("inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed", styles, className)}
    >
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  const { tr } = useLang();
  return <span role="status" aria-label={tr("Loading")} className={cx("inline-block animate-spin rounded-full border-2 border-current border-t-transparent", small ? "h-4 w-4" : "h-6 w-6")} />;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("rounded-xl border border-line bg-white p-4 shadow-sm sm:p-5", className)}>{children}</section>;
}

export function ErrorBox({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  const { tr } = useLang();
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
      <span className="flex-1">{typeof children === "string" ? localizeMessage(children, tr) : children}</span>
      {onRetry && <Button variant="secondary" onClick={onRetry}>{tr("Try again")}</Button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-white px-6 py-10 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Loading({ label }: { label?: string }) {
  const { tr } = useLang();
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted">
      <Spinner /> <span className="text-sm">{label ?? tr("Loading...")}</span>
    </div>
  );
}

const TONES: Record<string, string> = {
  ok: "bg-green-50 text-green-800 border-green-200",
  warn: "bg-amber-50 text-amber-900 border-amber-200",
  bad: "bg-red-50 text-red-800 border-red-200",
  info: "bg-blue-50 text-blue-800 border-blue-200",
  neutral: "bg-neutral-100 text-neutral-700 border-neutral-200",
};
export function Badge({ tone = "neutral", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return <span className={cx("inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold", TONES[tone])}>{children}</span>;
}

export const statusTone = (s: string): keyof typeof TONES =>
  ["verified", "approved", "paid", "succeeded", "activated", "done", "ok", "pass"].includes(s) ? "ok"
    : ["needs_review", "review", "pending", "awaiting_documents", "processing", "created", "installing", "install_scheduled", "warn", "kyc_verified", "placed"].includes(s) ? "warn"
    : ["rejected", "failed", "expired", "action_required", "incomplete", "cancelled", "fail", "missing"].includes(s) ? "bad" : "neutral";

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: string; error?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium">{label}</label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-700">{error}</p>}
    </div>
  );
}

export const inputCls = "block min-h-11 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm placeholder:text-neutral-400 focus:border-brand";
