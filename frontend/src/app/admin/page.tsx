"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { fmtDate, rupees, titleCase } from "@/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Loading, cx, inputCls, statusTone } from "@/components/ui";

const RED = "#e40000", INK = "#1c1c21", GREY = "#9a9ca6";
const TABS = ["Overview", "Segments", "Leads", "Orders", "KYC queue", "Advisor leads"] as const;
type Tab = (typeof TABS)[number];

interface Kpis { leads: number; activated: number; lead_to_activation_pct: number; avg_days_to_activation: number; avg_follow_up_calls: number; cac_per_activated_inr: number;
  median_monthly_bundle_inr: number; churn_6m_pct: number; avg_nps: number; activation_with_gstin_pct: number; activation_without_gstin_pct: number }
interface Overview { historical: Kpis; live: { journeys: number; quoted: number; orders: number; paid_orders: number; activated: number; journey_to_order_pct: number; monthly_value_booked: number; setup_value_booked: number; orders_by_status: Record<string, number>; orders_by_kyc: Record<string, number> } }
interface FunnelData { funnel: { stage: string; count: number; pct_of_previous: number | null; pct_of_leads: number }[]; drop_reasons: { reason: string; stage: string; count: number }[]; weekly: { week: string; leads: number; activated: number }[] }
interface Seg { key: string; leads: number; share_pct: number; activated: number; conversion_pct: number; avg_cac_inr: number; avg_monthly_value_inr: number; churn_pct: number | null; avg_nps: number | null; avg_days: number | null; monthly_revenue_per_acq_inr: number | null }
interface Prod { product_id: string; name: string; customers: number; attach_pct: number }
interface Lead { lead_id: string; business_name: string; business_type: string; segment: string; city: string; lead_source: string; stage_reached: string; outcome: string; drop_reason: string; employee_count: number; num_sites: number; has_gstin: string; propensity: number }
interface KycRow { order_id: string; business_name: string; status: string; summary: string | null; issues: { code: string; message: string; severity: string }[]; updated_at: string }
interface AdvLead { journey_id: string; business_name: string; city: string; segment: string; stage: string; propensity: number; employees: number; sites: number; phone: string | null }

const shortLabel = (k: string) => k.replace("Small multi-site businesses", "Multi-site").replace("Small manufacturers", "Manufacturers").replace("Micro retail & services", "Micro retail").replace("Professional offices", "Professional").replace("Channel partner", "Partner").replace("WhatsApp campaign", "WhatsApp");

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <Card className="!p-4"><p className="text-xs uppercase tracking-wide text-muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p>{sub && <p className="text-xs text-muted">{sub}</p>}</Card>;
}

function useFetch<T>(path: string, enabled: boolean) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => { setErr(""); api<T>(path).then(setData).catch((e: ApiError) => setErr(e.message)); }, [path]);
  useEffect(() => { if (enabled) load(); }, [enabled, load]);
  return { data, err, reload: load };
}

function OverviewTab() {
  const ov = useFetch<Overview>("/admin/overview", true);
  const fn = useFetch<FunnelData>("/admin/funnel", true);
  const pr = useFetch<{ auc_holdout: number; top_drivers: { feature: string; weight: number }[] }>("/admin/propensity", true);
  if (ov.err || fn.err) return <ErrorBox onRetry={() => { ov.reload(); fn.reload(); }}>{ov.err || fn.err}</ErrorBox>;
  if (!ov.data || !fn.data) return <Loading />;
  const h = ov.data.historical, l = ov.data.live;
  const dropByReason = Object.values(fn.data.drop_reasons.reduce<Record<string, { reason: string; count: number }>>((a, d) => { (a[d.reason] ??= { reason: d.reason, count: 0 }).count += d.count; return a; }, {})).sort((a, b) => b.count - a.count).slice(0, 10);
  return (
    <div className="space-y-5">
      <div>
        <p className="mb-2 text-sm font-semibold">Apr-Jun 2026 baseline (supplied leads dataset)</p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Lead → activation" value={`${h.lead_to_activation_pct}%`} sub={`${h.activated} of ${h.leads.toLocaleString("en-IN")} leads`} />
          <Stat label="Days to activate" value={`${h.avg_days_to_activation}`} sub={`${h.avg_follow_up_calls} chase calls on average`} />
          <Stat label="Acquisition cost" value={rupees(h.cac_per_activated_inr)} sub="per activated customer" />
          <Stat label="6-month churn" value={`${h.churn_6m_pct}%`} sub={`NPS ${h.avg_nps}`} />
          <Stat label="Median bundle" value={`${rupees(h.median_monthly_bundle_inr)}/mo`} />
          <Stat label="With GSTIN" value={`${h.activation_with_gstin_pct}%`} sub="activate" />
          <Stat label="Without GSTIN" value={`${h.activation_without_gstin_pct}%`} sub="activate" />
          <Stat label="Propensity model" value={pr.data ? `AUC ${pr.data.auc_holdout}` : "-"} sub="hold-out, profile features only" />
        </div>
      </div>
      <div>
        <p className="mb-2 text-sm font-semibold">Live platform (this prototype)</p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Advisor journeys" value={`${l.journeys}`} sub={`${l.quoted} reached a quote`} />
          <Stat label="Orders" value={`${l.orders}`} sub={`${l.journey_to_order_pct}% of journeys`} />
          <Stat label="Paid / activated" value={`${l.paid_orders} / ${l.activated}`} />
          <Stat label="Booked monthly value" value={rupees(l.monthly_value_booked)} sub={`+ ${rupees(l.setup_value_booked)} setup`} />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <p className="mb-2 font-semibold">Acquisition funnel</p>
          <div className="h-72" role="img" aria-label="Funnel bar chart">
            <ResponsiveContainer><BarChart data={fn.data.funnel} layout="vertical" margin={{ left: 20, right: 40 }}>
              <CartesianGrid horizontal={false} stroke="#eee" /><XAxis type="number" /><YAxis type="category" dataKey="stage" width={105} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v, _n, p) => [`${v} (${(p.payload as { pct_of_leads: number }).pct_of_leads}% of leads)`, "Leads"]} />
              <Bar isAnimationActive={false} dataKey="count" radius={[0, 4, 4, 0]} label={{ position: "right", fontSize: 12 }}>{fn.data.funnel.map((_, i) => <Cell key={i} fill={i === fn.data!.funnel.length - 1 ? RED : INK} />)}</Bar>
            </BarChart></ResponsiveContainer>
          </div>
          <p className="text-xs text-muted">Biggest leak: needs assessed → quote accepted ({fn.data.funnel[3].pct_of_previous}%). Price, quote complexity and quote delay are the top reasons there.</p>
        </Card>
        <Card>
          <p className="mb-2 font-semibold">Why leads dropped (top 10)</p>
          <div className="h-72" role="img" aria-label="Drop reasons bar chart">
            <ResponsiveContainer><BarChart data={dropByReason} layout="vertical" margin={{ left: 30, right: 30 }}>
              <CartesianGrid horizontal={false} stroke="#eee" /><XAxis type="number" /><YAxis type="category" dataKey="reason" width={170} tick={{ fontSize: 11 }} />
              <Tooltip /><Bar isAnimationActive={false} dataKey="count" fill={RED} radius={[0, 4, 4, 0]} />
            </BarChart></ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Card>
        <p className="mb-2 font-semibold">Weekly leads vs activations</p>
        <div className="h-64" role="img" aria-label="Weekly line chart">
          <ResponsiveContainer><LineChart data={fn.data.weekly}><CartesianGrid stroke="#eee" /><XAxis dataKey="week" tick={{ fontSize: 11 }} /><YAxis /><Tooltip /><Legend />
            <Line isAnimationActive={false} type="monotone" dataKey="leads" stroke={INK} strokeWidth={2} dot={false} /><Line isAnimationActive={false} type="monotone" dataKey="activated" stroke={RED} strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer>
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card><p className="mb-2 font-semibold">Live orders by status</p>{Object.keys(l.orders_by_status).length ? <ul className="space-y-1 text-sm">{Object.entries(l.orders_by_status).map(([k, v]) => <li key={k} className="flex justify-between"><Badge tone={statusTone(k)}>{titleCase(k)}</Badge><b>{v}</b></li>)}</ul> : <p className="text-sm text-muted">No orders yet.</p>}</Card>
        <Card><p className="mb-2 font-semibold">KYC status of live orders</p>{Object.keys(l.orders_by_kyc).length ? <ul className="space-y-1 text-sm">{Object.entries(l.orders_by_kyc).map(([k, v]) => <li key={k} className="flex justify-between"><Badge tone={statusTone(k)}>{titleCase(k)}</Badge><b>{v}</b></li>)}</ul> : <p className="text-sm text-muted">No KYC activity yet.</p>}</Card>
      </div>
      {pr.data && <Card><p className="font-semibold">What drives conversion (propensity model weights)</p><ul className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">{pr.data.top_drivers.map((d) => <li key={d.feature} className="flex justify-between"><span>{d.feature.replace(/_/g, " ")}</span><b className={d.weight >= 0 ? "text-ok" : "text-red-700"}>{d.weight > 0 ? "+" : ""}{d.weight}</b></li>)}</ul></Card>}
    </div>
  );
}

function SegmentsTab() {
  const seg = useFetch<{ segments: Seg[]; products: Prod[] }>("/admin/segments", true);
  const src = useFetch<{ rows: { key: string; leads: number; conversion_pct: number; avg_cac_inr: number }[] }>("/admin/breakdown/source", true);
  if (seg.err) return <ErrorBox onRetry={seg.reload}>{seg.err}</ErrorBox>;
  if (!seg.data) return <Loading />;
  return (
    <div className="space-y-5">
      <Card className="!p-0 overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-neutral-50 text-left text-xs uppercase text-muted"><tr><th className="px-4 py-2">Segment</th><th className="px-2">Share</th><th className="px-2">Leads</th><th className="px-2">Conv.</th><th className="px-2">CAC/lead</th><th className="px-2">Avg bundle/mo</th><th className="px-2">Churn</th><th className="px-2">NPS</th><th className="px-2">₹ MRR per ₹ spent</th></tr></thead>
          <tbody className="divide-y divide-line">{seg.data.segments.map((s) => (
            <tr key={s.key}><td className="px-4 py-3 font-medium">{s.key}</td><td className="px-2">{s.share_pct}%</td><td className="px-2">{s.leads.toLocaleString("en-IN")}</td><td className="px-2 font-semibold">{s.conversion_pct}%</td><td className="px-2">{rupees(s.avg_cac_inr)}</td><td className="px-2">{rupees(s.avg_monthly_value_inr)}</td><td className="px-2">{s.churn_pct}%</td><td className="px-2">{s.avg_nps}</td><td className="px-2">{s.monthly_revenue_per_acq_inr}</td></tr>))}</tbody>
        </table>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><p className="mb-2 font-semibold">Conversion by segment (%)</p>
          <div className="h-60" role="img" aria-label="Conversion by segment"><ResponsiveContainer><BarChart data={seg.data.segments}><CartesianGrid vertical={false} stroke="#eee" /><XAxis dataKey="key" tick={{ fontSize: 10 }} interval={0} tickFormatter={shortLabel} /><YAxis /><Tooltip /><Bar isAnimationActive={false} dataKey="conversion_pct" fill={RED} radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></Card>
        <Card><p className="mb-2 font-semibold">Conversion by lead source (%)</p>
          {src.data ? <div className="h-60" role="img" aria-label="Conversion by source"><ResponsiveContainer><BarChart data={src.data.rows}><CartesianGrid vertical={false} stroke="#eee" /><XAxis dataKey="key" tick={{ fontSize: 10 }} interval={0} tickFormatter={shortLabel} /><YAxis /><Tooltip /><Bar isAnimationActive={false} dataKey="conversion_pct" fill={INK} radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div> : <Loading />}</Card>
      </div>
      <Card><p className="mb-2 font-semibold">What activated customers bought (share of 368)</p>
        <div className="h-[520px]" role="img" aria-label="Product attach rates"><ResponsiveContainer><BarChart data={seg.data.products.slice(0, 15)} layout="vertical" margin={{ left: 20 }}><CartesianGrid horizontal={false} stroke="#eee" /><XAxis type="number" unit="%" /><YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 11 }} interval={0} /><Tooltip /><Bar isAnimationActive={false} dataKey="attach_pct" fill={GREY} radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div></Card>
    </div>
  );
}

function LeadsTab() {
  const [q, setQ] = useState("");
  const [segment, setSegment] = useState("");
  const [openOnly, setOpenOnly] = useState(false);
  const [page, setPage] = useState(1);
  const path = `/admin/leads?page=${page}&size=15&sort=propensity${segment ? `&segment=${encodeURIComponent(segment)}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}${openOnly ? "&open_only=true" : ""}`;
  const d = useFetch<{ total: number; items: Lead[] }>(path, true);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input aria-label="Search leads" className={`${inputCls} max-w-xs`} placeholder="Search name, city or ID" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select aria-label="Segment" className={`${inputCls} max-w-xs`} value={segment} onChange={(e) => { setSegment(e.target.value); setPage(1); }}>
          <option value="">All segments</option><option>Micro retail &amp; services</option><option>Professional offices</option><option>Small multi-site businesses</option><option>Small manufacturers</option>
        </select>
        <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={openOnly} onChange={(e) => { setOpenOnly(e.target.checked); setPage(1); }} /> Re-engagement list (dropped early)</label>
      </div>
      {d.err && <ErrorBox onRetry={d.reload}>{d.err}</ErrorBox>}
      {!d.data && !d.err && <Loading />}
      {d.data && (d.data.items.length === 0 ? <Empty title="No leads match these filters" /> : (
        <Card className="!p-0 overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-neutral-50 text-left text-xs uppercase text-muted"><tr><th className="px-4 py-2">Lead</th><th className="px-2">Segment</th><th className="px-2">City</th><th className="px-2">Source</th><th className="px-2">Stage</th><th className="px-2">GSTIN</th><th className="px-2">Propensity</th></tr></thead>
            <tbody className="divide-y divide-line">{d.data.items.map((l) => (
              <tr key={l.lead_id}><td className="px-4 py-2"><p className="font-medium">{l.business_name}</p><p className="text-xs text-muted">{l.lead_id} · {l.employee_count} staff, {l.num_sites} site(s)</p></td><td className="px-2 text-xs">{l.segment}</td><td className="px-2">{l.city}</td><td className="px-2">{l.lead_source}</td>
                <td className="px-2"><Badge tone={l.outcome === "Activated" ? "ok" : "neutral"}>{l.stage_reached}</Badge>{l.drop_reason && <p className="text-xs text-muted">{l.drop_reason}</p>}</td><td className="px-2">{l.has_gstin}</td>
                <td className="px-2"><div className="flex items-center gap-2"><div className="h-2 w-16 rounded bg-neutral-200"><div className="h-2 rounded bg-brand" style={{ width: `${l.propensity}%` }} /></div><b>{l.propensity}</b></div></td></tr>))}</tbody>
          </table>
        </Card>
      ))}
      {d.data && <div className="flex items-center justify-between text-sm"><span className="text-muted">{d.data.total.toLocaleString("en-IN")} leads</span><div className="flex gap-2"><Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button variant="secondary" disabled={page * 15 >= d.data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>}
    </div>
  );
}

function OrdersTab() {
  const d = useFetch<Order[]>("/admin/orders", true);
  const [msg, setMsg] = useState("");
  async function move(id: string, to: string) {
    setMsg("");
    try { await api(`/admin/orders/${id}/advance`, { body: { to } }); d.reload(); } catch (e) { setMsg(e instanceof ApiError ? e.message : "Failed"); }
  }
  if (d.err) return <ErrorBox onRetry={d.reload}>{d.err}</ErrorBox>;
  if (!d.data) return <Loading />;
  if (!d.data.length) return <Empty title="No orders yet">Orders appear here as customers check out.</Empty>;
  return (
    <div className="space-y-3">
      {msg && <ErrorBox>{msg}</ErrorBox>}
      {d.data.map((o) => (
        <Card key={o.id} className="flex flex-wrap items-center justify-between gap-3">
          <div><Link href={`/orders/${o.id}`} className="font-mono text-sm font-semibold underline">{o.id}</Link><p className="text-sm text-muted">{o.business_name} · {o.customer} · {rupees(o.monthly_total, true)}/mo</p></div>
          <div className="flex flex-wrap items-center gap-2"><Badge tone={statusTone(o.status)}>{titleCase(o.status)}</Badge><Badge tone={statusTone(o.kyc_status)}>KYC {titleCase(o.kyc_status)}</Badge><Badge tone={statusTone(o.payment_status)}>{titleCase(o.payment_status)}</Badge>
            {o.status === "install_scheduled" && <Button onClick={() => move(o.id, "installing")}>Start installation</Button>}
            {o.status === "installing" && <Button onClick={() => move(o.id, "activated")}>Mark activated</Button>}
            {!["activated", "cancelled"].includes(o.status) && <Button variant="danger" onClick={() => move(o.id, "cancelled")}>Cancel</Button>}</div>
        </Card>
      ))}
    </div>
  );
}

function KycTab() {
  const d = useFetch<KycRow[]>("/admin/kyc", true);
  const [msg, setMsg] = useState("");
  async function decide(id: string, approve: boolean) {
    setMsg("");
    try { await api(`/admin/kyc/${id}/decision`, { body: { approve, note: approve ? "Approved after manual review." : "Rejected after manual review." } }); d.reload(); } catch (e) { setMsg(e instanceof ApiError ? e.message : "Failed"); }
  }
  if (d.err) return <ErrorBox onRetry={d.reload}>{d.err}</ErrorBox>;
  if (!d.data) return <Loading />;
  if (!d.data.length) return <Empty title="No KYC cases yet" />;
  return (
    <div className="space-y-3">
      {msg && <ErrorBox>{msg}</ErrorBox>}
      {d.data.map((k) => (
        <Card key={k.order_id}>
          <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-mono text-sm font-semibold">{k.order_id}</p><p className="text-sm text-muted">{k.business_name} · updated {fmtDate(k.updated_at)}</p></div><Badge tone={statusTone(k.status)}>{titleCase(k.status)}</Badge></div>
          {k.summary && <p className="mt-2 text-sm">{k.summary}</p>}
          {k.issues.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-muted">{k.issues.map((i, n) => <li key={n}>{i.message}</li>)}</ul>}
          {k.status === "needs_review" && <div className="mt-3 flex gap-2"><Button onClick={() => decide(k.order_id, true)}>Approve</Button><Button variant="danger" onClick={() => decide(k.order_id, false)}>Send back to customer</Button></div>}
        </Card>
      ))}
    </div>
  );
}

function AdvisorLeadsTab() {
  const d = useFetch<AdvLead[]>("/admin/advisor-leads", true);
  if (d.err) return <ErrorBox onRetry={d.reload}>{d.err}</ErrorBox>;
  if (!d.data) return <Loading />;
  if (!d.data.length) return <Empty title="No unclosed advisor journeys">Journeys that did not reach an order show up here, ranked by propensity - ideal for field-force and partner follow-up.</Empty>;
  return (
    <Card className="!p-0 overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm"><thead className="bg-neutral-50 text-left text-xs uppercase text-muted"><tr><th className="px-4 py-2">Business</th><th className="px-2">Segment</th><th className="px-2">Reached</th><th className="px-2">Phone</th><th className="px-2">Call priority</th></tr></thead>
        <tbody className="divide-y divide-line">{d.data.map((l) => <tr key={l.journey_id}><td className="px-4 py-2"><p className="font-medium">{l.business_name}</p><p className="text-xs text-muted">{l.city} · {l.employees} staff, {l.sites} site(s)</p></td><td className="px-2 text-xs">{l.segment}</td><td className="px-2"><Badge>{titleCase(l.stage)}</Badge></td><td className="px-2">{l.phone ?? "-"}</td><td className="px-2 font-bold">{l.propensity}</td></tr>)}</tbody></table>
    </Card>
  );
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>("Overview");
  if (loading) return <Loading />;
  if (!user || user.role !== "admin") return <div className="mx-auto max-w-xl px-4 py-12"><Empty title="Admin access only"><Link className="text-brand underline" href="/login?next=/admin">Sign in as an administrator</Link></Empty></div>;
  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6">
      <h1 className="text-2xl font-bold">Back-office dashboard</h1>
      <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={cx("min-h-11 whitespace-nowrap border-b-2 px-4 text-sm font-semibold", tab === t ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink")}>{t}</button>)}
      </div>
      {tab === "Overview" && <OverviewTab />}
      {tab === "Segments" && <SegmentsTab />}
      {tab === "Leads" && <LeadsTab />}
      {tab === "Orders" && <OrdersTab />}
      {tab === "KYC queue" && <KycTab />}
      {tab === "Advisor leads" && <AdvisorLeadsTab />}
    </div>
  );
}
