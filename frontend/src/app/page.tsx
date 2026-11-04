"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, journeyStore } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { rupees } from "@/lib/format";
import { Card } from "@/components/ui";

interface Stats { leads: number; avg_days_to_activation: number; follow_up_calls: number; products: number }
interface MetaBench { benchmarks: Record<string, { activated: number; median_monthly_value: number; avg_days_to_activation: number }> }

const SERVICES = [
  { icon: "📶", name: "Connectivity", desc: "Fibre, 5G AirFiber, leased lines, business SIMs, failover and SD-WAN" },
  { icon: "💬", name: "Communication", desc: "Cloud telephony, toll-free, bulk SMS and WhatsApp Business" },
  { icon: "☁️", name: "Cloud & productivity", desc: "Business email, 1 TB backup, website and GST-ready billing/POS" },
  { icon: "🛡️", name: "Security", desc: "Endpoint protection, managed firewall and secure guest Wi-Fi" },
  { icon: "📹", name: "IoT & physical", desc: "Cloud CCTV, machine monitoring and fleet tracking" },
];
const SEGMENTS = [
  { key: "Micro retail & services", ex: "Kirana, salon, pharmacy", need: "Reliable internet for UPI/POS, WhatsApp catalogue" },
  { key: "Professional offices", ex: "Clinic, CA firm, coaching centre", need: "Uptime, business email, cloud backup, data security" },
  { key: "Small multi-site businesses", ex: "Restaurant chain, 3-10 stores", need: "One bill, central management, CCTV, failover" },
  { key: "Small manufacturers", ex: "Auto-parts or textile unit", need: "Dedicated bandwidth, machine IoT, managed firewall" },
];

export default function Landing() {
  const { t } = useLang();
  const [stats, setStats] = useState<Stats | null>(null);
  const [bench, setBench] = useState<MetaBench["benchmarks"] | null>(null);
  const [hasJourney, setHasJourney] = useState(false);

  useEffect(() => {
    setHasJourney(!!journeyStore.get());
    api<Stats>("/public/stats").then(setStats).catch(() => {});
    api<MetaBench>("/meta").then((m) => setBench(m.benchmarks)).catch(() => {});
  }, []);

  const steps = [["s1", "s1d"], ["s2", "s2d"], ["s3", "s3d"], ["s4", "s4d"], ["s5", "s5d"]] as const;

  return (
    <>
      <section className="relative overflow-hidden bg-ink text-white">
        <div aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(228,0,0,0.55),transparent_55%)]" />
        <div className="relative mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:py-20 md:grid-cols-[1.4fr_1fr] md:items-center">
          <div>
            <p className="mb-3 inline-block rounded-full border border-white/30 px-3 py-1 text-xs font-medium tracking-wide">{t("tagline")}</p>
            <h1 className="text-3xl font-bold leading-tight sm:text-5xl">{t("hero_title")}</h1>
            <p className="mt-4 max-w-xl text-base text-white/80 sm:text-lg">{t("hero_sub")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/onboarding" className="inline-flex min-h-12 items-center rounded-lg bg-brand px-6 py-3 text-base font-semibold hover:bg-brand-dark">{t("cta")} →</Link>
              {hasJourney && <Link href="/advisor" className="inline-flex min-h-12 items-center rounded-lg border border-white/40 px-5 py-3 text-base font-semibold hover:bg-white/10">Resume my plan</Link>}
              <Link href="/orders" className="inline-flex min-h-12 items-center rounded-lg border border-white/40 px-5 py-3 text-base font-semibold hover:bg-white/10">{t("cta2")}</Link>
            </div>
          </div>
          <div className="rounded-2xl border border-white/15 bg-white/10 p-5 backdrop-blur">
            <p className="text-sm font-semibold uppercase tracking-wider text-white/70">Today vs. Udyam Digital</p>
            <dl className="mt-4 space-y-4">
              <div><dt className="text-xs text-white/60">Needs discovery</dt><dd className="text-sm"><s className="text-white/50">Sales visit, pitches the monthly target</s> → AI advisor in minutes</dd></div>
              <div><dt className="text-xs text-white/60">Quote</dt><dd className="text-sm"><s className="text-white/50">3-5 days, PDF with product codes</s> → live price with GST, instantly</dd></div>
              <div><dt className="text-xs text-white/60">KYC</dt><dd className="text-sm"><s className="text-white/50">Paper / email chasing</s> → upload, OCR, GSTIN &amp; Udyam check</dd></div>
              <div>
                <dt className="text-xs text-white/60">Activation</dt>
                <dd className="text-sm"><s className="text-white/50">{stats ? `${stats.avg_days_to_activation} days, ${stats.follow_up_calls.toFixed(0)} chase calls` : "17.6 days, 3 chase calls"}</s> → live tracker, no calls</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-bold">{t("how")}</h2>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map(([a, b], i) => (
            <li key={a} className="rounded-xl border border-line bg-white p-4">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-sm font-bold text-white">{i + 1}</span>
              <p className="mt-3 font-semibold">{t(a)}</p>
              <p className="mt-1 text-sm text-muted">{t(b)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-y border-line bg-white py-12">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-2xl font-bold">25 services, one bill</h2>
          <p className="mt-1 text-sm text-muted">Straight from the Accel Business catalogue. Eligibility and pricing are checked automatically for your city, size and registration.</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {SERVICES.map((s) => (
              <Card key={s.name}>
                <div className="text-2xl" aria-hidden>{s.icon}</div>
                <p className="mt-2 font-semibold">{s.name}</p>
                <p className="mt-1 text-sm text-muted">{s.desc}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-bold">Built for how small businesses really work</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SEGMENTS.map((s) => {
            const b = bench?.[s.key];
            return (
              <Card key={s.key}>
                <p className="font-semibold">{s.key}</p>
                <p className="text-xs text-brand">{s.ex}</p>
                <p className="mt-2 text-sm text-muted">{s.need}</p>
                {b && <p className="mt-3 text-sm">Typical bundle: <b>{rupees(b.median_monthly_value)}</b>/month</p>}
              </Card>
            );
          })}
        </div>
        <div className="mt-10 rounded-2xl bg-brand-soft p-6 text-center">
          <p className="text-lg font-semibold">Ready in about three minutes.</p>
          <Link href="/onboarding" className="mt-4 inline-flex min-h-12 items-center rounded-lg bg-brand px-6 py-3 font-semibold text-white hover:bg-brand-dark">{t("cta")} →</Link>
        </div>
      </section>
    </>
  );
}
