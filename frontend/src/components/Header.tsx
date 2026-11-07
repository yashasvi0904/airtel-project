"use client";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import LanguagePicker from "@/components/LanguagePicker";
import { InstallButton } from "@/components/Pwa";

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
  const { tr } = useLang();
  const [open, setOpen] = useState(false);
  const links = (
    <>
      {user && <Link onClick={() => setOpen(false)} href="/orders" className="flex min-h-11 items-center rounded px-3 hover:bg-neutral-100">{tr("My orders")}</Link>}
      {user?.role === "admin" && <Link onClick={() => setOpen(false)} href="/admin" className="flex min-h-11 items-center rounded px-3 hover:bg-neutral-100">{tr("Admin")}</Link>}
      <InstallButton className="flex min-h-11 items-center rounded px-3 text-left font-medium text-brand hover:bg-neutral-100" onDone={() => setOpen(false)} />
      {user ? (
        <button onClick={() => { signOut(); setOpen(false); }} className="flex min-h-11 items-center rounded px-3 text-left hover:bg-neutral-100">{tr("Sign out")} ({user.name.split(" ")[0]})</button>
      ) : (
        <Link onClick={() => setOpen(false)} href="/login" className="flex min-h-11 items-center rounded px-3 hover:bg-neutral-100">{tr("Sign in")}</Link>
      )}
    </>
  );
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" aria-label={tr("Home")} className="flex min-h-11 items-center"><Logo /></Link>
        <div className="flex items-center gap-2">
          <nav className="hidden items-center gap-1 text-sm font-medium sm:flex">{links}</nav>
          <LanguagePicker />
          <button className="min-h-11 rounded-lg border border-line px-4 text-sm font-medium sm:hidden" aria-expanded={open} onClick={() => setOpen(!open)}>
            {tr("Menu")}
          </button>
        </div>
      </div>
      {open && <nav className="flex flex-col gap-1 border-t border-line px-4 py-2 text-sm font-medium sm:hidden">{links}</nav>}
    </header>
  );
}
