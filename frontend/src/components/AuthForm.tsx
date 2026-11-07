"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import GoogleButton from "./GoogleButton";
import { Button, Card, ErrorBox, Field, inputCls } from "./ui";

function Form({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { tr } = useLang();
  const next = useSearchParams().get("next") || "/orders";
  const { signIn, register, googleSignIn } = useAuth();
  const [f, setF] = useState({ name: "", email: "", phone: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => setF((p) => ({ ...p, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    if (!f.email.trim() || !f.password) return setErr(tr("Enter your email and password"));
    if (mode === "register" && (!f.name.trim() || f.password.length < 8)) return setErr(tr("Enter your name and a password of at least 8 characters"));
    setBusy(true);
    try {
      if (mode === "login") await signIn(f.email.trim(), f.password);
      else await register({ email: f.email.trim(), name: f.name.trim(), password: f.password, phone: f.phone.trim() || undefined });
      router.push(next.startsWith("/") ? next : "/orders");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : tr("Something went wrong"));
    } finally {
      setBusy(false);
    }
  }

  async function onGoogle(credential: string) {
    setErr("");
    try {
      await googleSignIn(credential);
      router.push(next.startsWith("/") ? next : "/orders");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : tr("Google sign-in failed. Please try again."));
    }
  }

  const other = mode === "login" ? `/register?next=${encodeURIComponent(next)}` : `/login?next=${encodeURIComponent(next)}`;
  return (
    <div className="mx-auto max-w-md px-4 py-10">
      <Card>
        <h1 className="text-xl font-bold">{mode === "login" ? tr("Sign in") : tr("Create your account")}</h1>
        <p className="mt-1 text-sm text-muted">{mode === "login" ? tr("Track orders and continue where you left off.") : tr("One account to place orders, complete KYC and track installation.")}</p>
        <div className="mt-5">
          <GoogleButton mode={mode} onCredential={onGoogle} onError={setErr} />
          <div className="my-4 flex items-center gap-3 text-xs text-muted" aria-hidden><span className="h-px flex-1 bg-line" />{tr("or use email")}<span className="h-px flex-1 bg-line" /></div>
        </div>
        <form onSubmit={submit} className="space-y-4" noValidate>
          {mode === "register" && <Field label={tr("Full name")} htmlFor="name"><input id="name" autoComplete="name" className={inputCls} value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>}
          <Field label={tr("Email")} htmlFor="email"><input id="email" type="email" autoComplete="email" className={inputCls} value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
          {mode === "register" && <Field label={tr("Mobile (optional)")} htmlFor="phone"><input id="phone" type="tel" inputMode="tel" autoComplete="tel-national" className={inputCls} value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>}
          <Field label={tr("Password")} htmlFor="pw" hint={mode === "register" ? tr("At least 8 characters") : undefined}>
            <input id="pw" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} className={inputCls} value={f.password} onChange={(e) => set("password", e.target.value)} />
          </Field>
          {err && <ErrorBox>{err}</ErrorBox>}
          <Button type="submit" loading={busy} className="w-full">{mode === "login" ? tr("Sign in") : tr("Create account")}</Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted">
          {mode === "login" ? tr("New here?") : tr("Already registered?")}{" "}
          <Link href={other} className="inline-flex min-h-11 items-center font-semibold text-brand underline">{mode === "login" ? tr("Create an account") : tr("Sign in")}</Link>
        </p>
      </Card>
    </div>
  );
}

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  return <Suspense><Form mode={mode} /></Suspense>;
}
