"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, journeyStore } from "@/lib/api";
import { tx, useLang } from "@/lib/i18n";
import type { CatalogueItem, Journey, PreviewResult, Recommendation, SavedQuote } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, cx, inputCls } from "@/components/ui";

type Item = { product_id: string; quantity: number };
const TIERS = [
  { id: "starter", label: tx("Starter"), blurb: tx("What you asked for, nothing extra") },
  { id: "recommended", label: tx("Recommended"), blurb: tx("Adds what similar businesses rely on") },
  { id: "complete", label: tx("Complete"), blurb: tx("Everything useful for your size") },
] as const;

export default function BundlePage() {
  const router = useRouter();
  const { tr, lm, tn } = useLang();
  const [jid, setJid] = useState<string | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [catalogue, setCatalogue] = useState<CatalogueItem[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [term, setTerm] = useState(12);
  const [tier, setTier] = useState<string>("recommended");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [pricing, setPricing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [gstin, setGstin] = useState("");
  const [gstMsg, setGstMsg] = useState("");
  const [notice, setNotice] = useState("");
  const reasons = useMemo(() => {
    const m: Record<string, string[]> = {};
    if (rec) for (const t of Object.values(rec.tiers)) for (const i of t.items) m[i.product_id] = [...new Set([...(m[i.product_id] ?? []), ...i.reasons])];
    return m;
  }, [rec]);
  const byId = useMemo(() => Object.fromEntries(catalogue.map((c) => [c.product_id, c])), [catalogue]);

  const load = useCallback(async (silent = false) => {
    const id = journeyStore.get();
    setJid(id);
    if (!id) { setLoading(false); return; }
    if (!silent) setLoading(true);
    setErr("");
    try {
      const r = await api<{ journey: Journey; recommendation: Recommendation; catalogue: CatalogueItem[] }>(`/journeys/${id}/recommendations`);
      setJourney(r.journey);
      setRec(r.recommendation);
      setCatalogue(r.catalogue);
      const sel = r.journey.selection;
      if (sel?.items?.length) {
        setItems(sel.items);
        setTerm(sel.term_months);
        setTier(sel.tier ?? "custom");
      } else {
        const t = r.recommendation.tiers[r.recommendation.recommended_tier];
        setItems(t.items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })));
        setTerm(t.term_months);
        setTier(r.recommendation.recommended_tier);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) { journeyStore.set(null); setJid(null); } else setErr(e instanceof ApiError ? e.message : tn("Could not load recommendations"));
    } finally {
      setLoading(false);
    }
  }, [tn]);
  useEffect(() => { load(); }, [load]);

  // Dynamic recalculation: every change re-prices on the server (debounced, latest wins)
  const seq = useRef(0);
  useEffect(() => {
    if (!jid || !items.length) { setPreview(null); return; }
    const mine = ++seq.current;
    setPricing(true);
    const h = setTimeout(async () => {
      try {
        const p = await api<PreviewResult>("/quotes/preview", { body: { journey_id: jid, items, term_months: term } });
        if (mine === seq.current) setPreview(p);
      } catch (e) {
        if (mine === seq.current) setErr(e instanceof ApiError ? e.message : tn("Pricing failed"));
      } finally {
        if (mine === seq.current) setPricing(false);
      }
    }, 250);
    return () => clearTimeout(h);
  }, [jid, items, term, tn]);

  // keep the term valid when the product mix changes
  useEffect(() => {
    const opts = (preview?.quote ?? preview?.indicative_quote)?.totals.term_options;
    if (opts && !opts.includes(term)) setTerm(opts.includes(12) ? 12 : opts[0]);
  }, [preview, term]);

  const selectedIds = new Set(items.map((i) => i.product_id));
  const setQty = (pid: string, q: number) => setItems((its) => its.map((i) => (i.product_id === pid ? { ...i, quantity: Math.max(1, Math.min(1000, q || 1)) } : i)));
  const remove = (pid: string) => { setItems((its) => its.filter((i) => i.product_id !== pid)); setTier("custom"); };
  const add = (pid: string) => { if (!selectedIds.has(pid)) { setItems((its) => [...its, { product_id: pid, quantity: byId[pid]?.default_quantity ?? 1 }]); setTier("custom"); } };
  const pickTier = (t: (typeof TIERS)[number]["id"]) => {
    if (!rec) return;
    setItems(rec.tiers[t].items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })));
    setTerm(rec.tiers[t].term_months);
    setTier(t);
  };

  async function addGstin() {
    if (!jid) return;
    setGstMsg("");
    try {
      await api(`/journeys/${jid}/profile`, { method: "PATCH", body: { gstin: gstin.trim().toUpperCase() } });
      setGstin("");
      setGstMsg("");
      setNotice(tr("GSTIN verified - GSTIN-only products are now unlocked. Your selection was reset to the updated recommendation."));
      await load(true);
    } catch (e) {
      setGstMsg(e instanceof ApiError ? e.message : tr("Could not verify GSTIN"));
    }
  }

  async function proceed() {
    if (!jid) return;
    setSaving(true);
    setErr("");
    try {
      const s = await api<PreviewResult>(`/journeys/${jid}/selection`, { method: "PUT", body: { items, term_months: term } });
      if (!s.valid) { setPreview(s); setErr(tr("Please fix the highlighted problems first.")); return; }
      const q = await api<SavedQuote>(`/journeys/${jid}/quote`, { method: "POST" });
      router.push(`/checkout?quote=${q.id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : tr("Could not create your quote"));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading label={tr("Preparing your bundle...")} />;
  if (!jid || !journey || !rec) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        {err ? <ErrorBox onRetry={() => load()}>{err}</ErrorBox> : <Empty title={tr("No bundle yet")}><Link href="/onboarding" className="text-brand underline">{tr("Start with your business details")}</Link></Empty>}
      </div>
    );
  }

  const quote = preview?.quote ?? preview?.indicative_quote ?? null;
  const t = quote?.totals;
  const optional = catalogue.filter((c) => !selectedIds.has(c.product_id));
  const grouped = optional.reduce<Record<string, CatalogueItem[]>>((acc, c) => { (acc[c.category] ??= []).push(c); return acc; }, {});
  const needsGstin = journey.profile.gstin_status === "none" || journey.profile.gstin_status === "declared";

  return (
    <div className="mx-auto grid max-w-6xl gap-5 px-4 py-4 pb-28 lg:grid-cols-[1fr_360px] lg:py-6 lg:pb-6">
      <div className="space-y-5">
        <div>
          <h1 className="text-2xl font-bold">{tr("Your bundle for {name}", { name: journey.profile.business_name })}</h1>
          <p className="text-sm text-muted">{tr("Picked by our rules engine from the Accel Business catalogue for a {segment} in a tier {tier} city.", { segment: tr(journey.profile.segment).toLowerCase(), tier: journey.profile.city_tier })}</p>
        </div>

        <div className="grid gap-2 sm:grid-cols-3" role="tablist" aria-label={tr("Bundle options")}>
          {TIERS.map((x) => {
            const q = rec.tiers[x.id].quote?.totals.monthly_total;
            return (
              <button key={x.id} role="tab" aria-selected={tier === x.id} onClick={() => pickTier(x.id)}
                className={cx("rounded-xl border p-3 text-left transition", tier === x.id ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-line bg-white hover:border-neutral-400")}>
                <span className="flex items-center justify-between text-sm font-semibold">{tr(x.label)}{rec.recommended_tier === x.id && <Badge tone="ok">{tr("Best fit")}</Badge>}</span>
                <span className="block text-xs text-muted">{tr(x.blurb)}</span>
                <span className="mt-1 block text-sm font-bold">{rupees(q)}<span className="text-xs font-normal text-muted">{tr("/mo incl. GST")}</span></span>
              </button>
            );
          })}
        </div>

        {notice && <p role="status" className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900">{notice}</p>}
        {rec.over_budget && <ErrorBox>{tr("Even the essentials are above your {budget} monthly budget. You can remove items below or pick a longer term to bring the price down.", { budget: rupees(rec.budget) })}</ErrorBox>}
        {rec.notes.map((n) => <p key={n} className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-900">{lm(n)}</p>)}

        <Card className="!p-0">
          <div className="border-b border-line px-4 py-3 font-semibold">{tr("In your bundle ({n})", { n: items.length })}</div>
          {items.length === 0 && <div className="p-6"><Empty title={tr("Nothing selected")}>{tr("Pick a bundle above or add products below.")}</Empty></div>}
          <ul className="divide-y divide-line">
            {items.map((it) => {
              const p = byId[it.product_id];
              const line = quote?.items.find((l) => l.product_id === it.product_id);
              const errs = preview?.errors.filter((e) => e.product_id === it.product_id) ?? [];
              if (!p) return null;
              return (
                <li key={it.product_id} className={cx("px-4 py-4", errs.length > 0 && "bg-red-50")}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">{p.name} <span className="text-xs font-normal text-muted">{tr(p.category)}</span></p>
                      <p className="text-sm text-muted">{tr(p.description)}</p>
                      {reasons[it.product_id]?.[0] && <p className="mt-1 text-sm text-ink"><span className="font-medium text-brand">{tr("Why:")} </span>{lm(reasons[it.product_id][0])}</p>}
                      {p.requires_one_of.length > 0 && <p className="mt-1 text-xs text-muted">{tr("Needs one of: {list}", { list: p.requires_one_of.map((d) => byId[d]?.name ?? d).join(", ") })}</p>}
                      {errs.map((e) => <p key={e.code + e.message} className="mt-1 text-sm font-medium text-red-700">{lm(e.message)}</p>)}
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <div className="flex items-center gap-1" aria-label={tr("Quantity ({unit})", { unit: tr(p.unit) })}>
                        <button className="h-11 w-11 rounded-lg border border-line text-xl" aria-label={tr("Decrease")} onClick={() => setQty(it.product_id, it.quantity - 1)}>−</button>
                        <input aria-label={tr("Quantity")} inputMode="numeric" className="h-11 w-14 rounded-lg border border-line text-center text-base" value={it.quantity} onChange={(e) => setQty(it.product_id, parseInt(e.target.value.replace(/\D/g, ""), 10))} />
                        <button className="h-11 w-11 rounded-lg border border-line text-xl" aria-label={tr("Increase")} onClick={() => setQty(it.product_id, it.quantity + 1)}>+</button>
                      </div>
                      <span className="text-xs text-muted">{tr(p.unit)}</span>
                      <span className="text-sm font-bold">{line ? `${rupees(line.monthly)}${tr("/mo")}` : "..."}</span>
                      <button className="inline-flex min-h-11 items-center px-2 text-sm text-brand underline" onClick={() => remove(it.product_id)}>{tr("Remove")}</button>
                    </div>
                  </div>
                  {line && <p className="mt-1 text-xs text-muted">{tr("{price} {unit} (list {list})", { price: rupees(line.unit_price), unit: tr(p.unit), list: rupees(line.list_unit_price) })}{line.setup > 0 && ` · ${tr("setup")} ${rupees(line.setup)}`}{line.discounts.length > 0 && ` · ${line.discounts.map((d) => lm(d.label)).join(", ")}`}</p>}
                </li>
              );
            })}
          </ul>
        </Card>

        {preview && preview.fixes.length > 0 && (
          <Card className="border-amber-300 bg-amber-50">
            <p className="font-semibold">{tr("Some products depend on others")}</p>
            {preview.fixes.map((f) => (
              <div key={f.product_id} className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                <span>{tr("{name} needs a connection:", { name: byId[f.product_id]?.name ?? "" })}</span>
                {f.add_one_of.map((o) => <Button key={o.product_id} variant="secondary" onClick={() => add(o.product_id)}>{tr("Add {name}", { name: o.name })}</Button>)}
                <Button variant="ghost" onClick={() => remove(f.or_remove)}>{tr("Or remove it")}</Button>
              </div>
            ))}
          </Card>
        )}

        <div>
          <button className="inline-flex min-h-11 items-center text-sm font-semibold text-brand underline" onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
            {showAll ? tr("Hide all other products ({n})", { n: optional.length }) : tr("Browse all other products ({n})", { n: optional.length })}
          </button>
          {showAll && (
            <div className="mt-3 space-y-4">
              {needsGstin && (
                <Card className="bg-brand-soft">
                  <p className="text-sm font-semibold">{tr("Unlock GSTIN-only products")}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <input className={`${inputCls} max-w-xs font-mono uppercase`} aria-label="GSTIN" autoCapitalize="characters" autoComplete="off" spellCheck={false} placeholder={tr("Enter your 15-character GSTIN")} value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 15))} />
                    <Button onClick={addGstin} disabled={gstin.length !== 15}>{tr("Verify")}</Button>
                  </div>
                  {gstMsg && <p className="mt-2 text-sm">{gstMsg}</p>}
                </Card>
              )}
              {Object.entries(grouped).map(([cat, list]) => (
                <div key={cat}>
                  <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{tr(cat)}</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {list.map((p) => {
                      const ok = p.eligibility.status !== "no";
                      return (
                        <Card key={p.product_id} className={cx(!ok && "bg-neutral-50")}>
                          <div className="flex items-start justify-between gap-2">
                            <p className="font-semibold">{p.name}</p>
                            {p.eligibility.status === "conditional" && <Badge tone="warn">{tr("GSTIN to verify")}</Badge>}
                            {!ok && <Badge tone="bad">{tr("Not available")}</Badge>}
                          </div>
                          <p className="mt-1 text-sm text-muted">{tr(p.description)}</p>
                          <p className="mt-2 text-sm">{rupees(p.price_min)}-{rupees(p.price_max)} {tr(p.unit)}{p.setup_fee > 0 && ` · ${tr("setup")} ${rupees(p.setup_fee)}`}</p>
                          {p.segment_attach_rate >= 0.1 && <p className="text-xs text-muted">{tr("{pct}% of similar customers bought this", { pct: Math.round(p.segment_attach_rate * 100) })}</p>}
                          {!ok && <p className="mt-2 text-xs text-red-700">{p.eligibility.reasons.map((r) => lm(r.message)).join(" ")}{p.eligibility.unlock[0] && ` ${tr("{step} to unlock.", { step: lm(p.eligibility.unlock[0]) })}`}</p>}
                          <Button variant="secondary" className="mt-3 w-full" disabled={!ok} onClick={() => add(p.product_id)}>{tr("Add to bundle")}</Button>
                        </Card>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        {rec.excluded.length > 0 && (
          <p className="text-xs text-muted">{tr("Not offered to you right now:")} {rec.excluded.map((e) => `${e.name} (${lm(e.eligibility.reasons[0]?.message ?? "")})`).join("; ")}</p>
        )}
      </div>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        <Card className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="font-semibold">{tr("Your price")}</p>
            {pricing && <span className="text-xs text-muted">{tr("Updating...")}</span>}
          </div>
          {t ? (
            <>
              <Field label={tr("Contract length")} htmlFor="term">
                <select id="term" className={inputCls} value={term} onChange={(e) => setTerm(Number(e.target.value))}>
                  {t.term_options.map((o) => <option key={o} value={o}>{o === 24 ? tr("{n} months - lowest price", { n: o }) : o > 1 ? tr("{n} months", { n: o }) : tr("{n} month", { n: o })}</option>)}
                </select>
              </Field>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>{tr("Monthly (before GST)")}</dt><dd>{rupees(t.monthly_subtotal, true)}</dd></div>
                <div className="flex justify-between text-muted"><dt>{tr("GST @ {rate}%", { rate: t.gst_rate_percent })}</dt><dd>{rupees(t.monthly_gst, true)}</dd></div>
                <div className="flex justify-between border-t border-line pt-2 text-lg font-bold"><dt>{tr("Per month")}</dt><dd>{rupees(t.monthly_total, true)}</dd></div>
                <div className="flex justify-between pt-2"><dt>{tr("One-time setup (incl. GST)")}</dt><dd>{rupees(t.setup_total, true)}</dd></div>
                <div className="flex justify-between text-muted"><dt>{tr("First payment")}</dt><dd>{rupees(t.first_payment, true)}</dd></div>
              </dl>
              {t.discount_vs_list > 0 && <p className="rounded-lg bg-green-50 px-3 py-2 text-xs text-green-800">{tr("You save {amount}/month vs list price with this term and bundle.", { amount: rupees(t.discount_vs_list, true) })}</p>}
              {t.vs_current_spend !== undefined && <p className="text-xs text-muted">{tr("vs. your current {current}: {diff}/month before GST", { current: rupees(t.current_monthly_spend), diff: (t.vs_current_spend >= 0 ? "+" : "−") + rupees(Math.abs(t.vs_current_spend)) })}</p>}
              {journey.profile.monthly_budget && (
                <p className={cx("text-xs font-medium", t.monthly_total <= journey.profile.monthly_budget ? "text-ok" : "text-red-700")}>
                  {t.monthly_total <= journey.profile.monthly_budget ? "✓ " + tr("Within your {budget} budget", { budget: rupees(journey.profile.monthly_budget) }) : tr("Above your {budget} budget", { budget: rupees(journey.profile.monthly_budget) })}
                </p>
              )}
              <p className="text-xs text-muted">{tr("Installation about {days} days after KYC.", { days: t.install_days })} {lm(t.gst_note)}</p>
            </>
          ) : <p className="text-sm text-muted">{items.length ? tr("Calculating...") : tr("Add a product to see your price.")}</p>}
          {err && <ErrorBox>{err}</ErrorBox>}
          <Button className="w-full" onClick={proceed} loading={saving} disabled={!items.length || pricing || (preview ? !preview.valid : true)}>{tr("Get quote & checkout")} →</Button>
          <Link href="/advisor" className="flex min-h-11 items-center justify-center text-sm text-brand underline">{tr("Back to advisor")}</Link>
        </Card>
      </aside>
      <div className="fixed inset-x-0 bottom-0 z-20 flex items-center gap-3 border-t border-line bg-white p-3 shadow-[0_-4px_12px_rgba(0,0,0,0.08)] lg:hidden">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted">{tr("Per month")}</p>
          <p className="truncate text-lg font-bold">{t ? rupees(t.monthly_total, true) : "..."}</p>
        </div>
        <Button className="shrink-0" onClick={proceed} loading={saving} disabled={!items.length || pricing || (preview ? !preview.valid : true)}>{tr("Get quote & checkout")} →</Button>
      </div>
    </div>
  );
}
