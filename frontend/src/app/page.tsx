"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, journeyStore } from "@/lib/api";
import { tx, useLang } from "@/lib/i18n";
import { rupees } from "@/lib/format";
import { Card } from "@/components/ui";
import { LanguageChips } from "@/components/LanguagePicker";

interface Stats { leads: number; avg_days_to_activation: number; follow_up_calls: number; products: number }
interface MetaBench { benchmarks: Record<string, { activated: number; median_monthly_value: number; avg_days_to_activation: number }> }

const SERVICES = [
  { icon: "📶", name: tx("Connectivity"), desc: tx("Fibre, 5G AirFiber, leased lines, business SIMs, failover and SD-WAN") },
  { icon: "💬", name: tx("Communication"), desc: tx("Cloud telephony, toll-free, bulk SMS and WhatsApp Business") },
  { icon: "☁️", name: tx("Cloud & productivity"), desc: tx("Business email, 1 TB backup, website and GST-ready billing/POS") },
  { icon: "🛡️", name: tx("Security"), desc: tx("Endpoint protection, managed firewall and secure guest Wi-Fi") },
  { icon: "📹", name: tx("IoT & physical"), desc: tx("Cloud CCTV, machine monitoring and fleet tracking") },
];
const SEGMENTS = [
  { key: tx("Micro retail & services"), ex: tx("Kirana, salon, pharmacy"), need: tx("Reliable internet for UPI/POS, WhatsApp catalogue") },
  { key: tx("Professional offices"), ex: tx("Clinic, CA firm, coaching centre"), need: tx("Uptime, business email, cloud backup, data security") },
  { key: tx("Small multi-site businesses"), ex: tx("Restaurant chain, 3-10 stores"), need: tx("One bill, central management, CCTV, failover") },
  { key: tx("Small manufacturers"), ex: tx("Auto-parts or textile unit"), need: tx("Dedicated bandwidth, machine IoT, managed firewall") },
];

export default function Landing() {
  const { tr } = useLang();
  const [stats, setStats] = useState<Stats | null>(null);
  const [bench, setBench] = useState<MetaBench["benchmarks"] | null>(null);
  const [hasJourney, setHasJourney] = useState(false);

  useEffect(() => {
    setHasJourney(!!journeyStore.get());
    api<Stats>("/public/stats").then(setStats).catch(() => {});
    api<MetaBench>("/meta").then((m) => setBench(m.benchmarks)).catch(() => {});
  }, []);

  const steps = [
    [tx("Tell us about your business"), tx("Type, size, city and budget - takes a minute.")],
    [tx("Chat with the advisor"), tx("A few simple questions, in your own language.")],
    [tx("See a clear monthly price"), tx("Toggle add-ons, pick 12 or 24 months, see GST upfront.")],
    [tx("Verify in minutes"), tx("Upload GST, Udyam, ID and bill. We check them instantly.")],
    [tx("Track to activation"), tx("Book the installation slot and follow every step - no chasing.")],
  ] as const;

  return (
    <>
      <section className="relative overflow-hidden bg-ink text-white">
        <div aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(228,0,0,0.55),transparent_55%)]" />
        <div className="relative mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:py-20 md:grid-cols-[1.4fr_1fr] md:items-center">
          <div className="min-w-0">
            <LanguageChips />
            <p className="mb-3 inline-block rounded-full border border-white/30 px-3 py-1 text-xs font-medium tracking-wide">{tr("Everything your business needs to go digital - in one sitting.")}</p>
            <h1 className="text-3xl font-bold leading-tight sm:text-5xl">{tr("Internet, SIMs, WhatsApp, CCTV and more - one plan, one bill, live in days.")}</h1>
            <p className="mt-4 max-w-xl text-base text-white/80 sm:text-lg">{tr("Tell our AI advisor about your business. Get a clear monthly price, verify your documents in minutes and track your installation online - no sales visit needed.")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/onboarding" className="inline-flex min-h-12 items-center rounded-lg bg-brand px-6 py-3 text-base font-semibold hover:bg-brand-dark">{tr("Build my plan")} →</Link>
              {hasJourney && <Link href="/advisor" className="inline-flex min-h-12 items-center rounded-lg border border-white/40 px-5 py-3 text-base font-semibold hover:bg-white/10">{tr("Resume my plan")}</Link>}
              <Link href="/orders" className="inline-flex min-h-12 items-center rounded-lg border border-white/40 px-5 py-3 text-base font-semibold hover:bg-white/10">{tr("Track my order")}</Link>
            </div>
          </div>
          <div className="min-w-0 rounded-2xl border border-white/15 bg-white/10 p-5 backdrop-blur">
            <p className="text-sm font-semibold uppercase tracking-wider text-white/70">{tr("Today vs. Udyam Digital")}</p>
            <dl className="mt-4 space-y-4">
              <div><dt className="text-xs text-white/60">{tr("Needs discovery")}</dt><dd className="text-sm"><s className="text-white/50">{tr("Sales visit, pitches the monthly target")}</s> → {tr("AI advisor in minutes")}</dd></div>
              <div><dt className="text-xs text-white/60">{tr("Quote")}</dt><dd className="text-sm"><s className="text-white/50">{tr("3-5 days, PDF with product codes")}</s> → {tr("live price with GST, instantly")}</dd></div>
              <div><dt className="text-xs text-white/60">KYC</dt><dd className="text-sm"><s className="text-white/50">{tr("Paper / email chasing")}</s> → {tr("upload, automatic reading, GSTIN and Udyam check")}</dd></div>
              <div>
                <dt className="text-xs text-white/60">{tr("Activation")}</dt>
                <dd className="text-sm"><s className="text-white/50">{stats ? tr("{days} days, {calls} chase calls", { days: stats.avg_days_to_activation, calls: stats.follow_up_calls.toFixed(0) }) : tr("{days} days, {calls} chase calls", { days: "17.6", calls: 3 })}</s> → {tr("live tracker, no calls")}</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-bold">{tr("How it works")}</h2>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map(([a, b], i) => (
            <li key={a} className="rounded-xl border border-line bg-white p-4">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-sm font-bold text-white">{i + 1}</span>
              <p className="mt-3 font-semibold">{tr(a)}</p>
              <p className="mt-1 text-sm text-muted">{tr(b)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-y border-line bg-white py-12">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-2xl font-bold">{tr("25 services, one bill")}</h2>
          <p className="mt-1 text-sm text-muted">{tr("Straight from the Accel Business catalogue. Eligibility and pricing are checked automatically for your city, size and registration.")}</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {SERVICES.map((s) => (
              <Card key={s.name}>
                <div className="text-2xl" aria-hidden>{s.icon}</div>
                <p className="mt-2 font-semibold">{tr(s.name)}</p>
                <p className="mt-1 text-sm text-muted">{tr(s.desc)}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-bold">{tr("Built for how small businesses really work")}</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SEGMENTS.map((s) => {
            const b = bench?.[s.key];
            return (
              <Card key={s.key}>
                <p className="font-semibold">{tr(s.key)}</p>
                <p className="text-xs text-brand">{tr(s.ex)}</p>
                <p className="mt-2 text-sm text-muted">{tr(s.need)}</p>
                {b && <p className="mt-3 text-sm">{tr("Typical bundle: {amount}/month", { amount: rupees(b.median_monthly_value) })}</p>}
              </Card>
            );
          })}
        </div>
        <div className="mt-10 rounded-2xl bg-brand-soft p-6 text-center">
          <p className="text-lg font-semibold">{tr("Ready in about three minutes.")}</p>
          <Link href="/onboarding" className="mt-4 inline-flex min-h-12 items-center rounded-lg bg-brand px-6 py-3 font-semibold text-white hover:bg-brand-dark">{tr("Build my plan")} →</Link>
        </div>
      </section>
    </>
  );
}
