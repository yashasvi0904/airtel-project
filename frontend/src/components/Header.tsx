"use client";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";

export function Logo() {
  return (
    <span className="flex items-center gap-2 font-bold tracking-tight">
      <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-lg leading-none text-white">a</span>
      <span className="leading-tight">
        <span className="block text-base">accel business</span>
        <span className="block text-[10px] font-medium uppercase tracking-widest text-brand">Udyam Digital</span>
      </span>
    </span>
  );
}

export default function Header() {
  const { user, signOut } = useAuth();
  const { lang, setLang, t } = useLang();
  const [open, setOpen] = useState(false);
  const links = (
    <>
      {user && <Link onClick={() => setOpen(false)} href="/orders" className="rounded px-3 py-2 hover:bg-neutral-100">{t("nav_orders")}</Link>}
      {user?.role === "admin" && <Link onClick={() => setOpen(false)} href="/admin" className="rounded px-3 py-2 hover:bg-neutral-100">{t("nav_admin")}</Link>}
      {user ? (
        <button onClick={() => { signOut(); setOpen(false); }} className="rounded px-3 py-2 text-left hover:bg-neutral-100">{t("nav_signout")} ({user.name.split(" ")[0]})</button>
      ) : (
        <Link onClick={() => setOpen(false)} href="/login" className="rounded px-3 py-2 hover:bg-neutral-100">{t("nav_signin")}</Link>
      )}
      <button
        onClick={() => setLang(lang === "en" ? "hi" : "en")}
        aria-label="Switch language"
        className="rounded border border-line px-3 py-2 text-left text-xs font-semibold hover:bg-neutral-100"
      >
        {lang === "en" ? "हिन्दी" : "English"}
      </button>
    </>
  );
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" aria-label="Home"><Logo /></Link>
        <nav className="hidden items-center gap-1 text-sm font-medium sm:flex">{links}</nav>
        <button className="rounded border border-line px-3 py-2 text-sm sm:hidden" aria-expanded={open} onClick={() => setOpen(!open)}>
          Menu
        </button>
      </div>
      {open && <nav className="flex flex-col gap-1 border-t border-line px-4 py-2 text-sm font-medium sm:hidden">{links}</nav>}
    </header>
  );
}
