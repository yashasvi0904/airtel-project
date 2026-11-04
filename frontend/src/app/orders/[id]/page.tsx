"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { fmtDate, fmtDateTime, rupees, titleCase } from "@/lib/format";
import Tracker from "@/components/Tracker";
import { Badge, Button, Card, Empty, ErrorBox, Loading, cx, statusTone } from "@/components/ui";

interface Slot { date: string; weekday: string; windows: { id: string; label: string }[] }

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [err, setErr] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [pick, setPick] = useState<{ date: string; window: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setErr("");
    try { setOrder(await api<Order>(`/orders/${id}`)); }
    catch (e) { setErr(e instanceof ApiError ? (e.status === 404 ? "We could not find this order on your account." : e.message) : "Could not load the order"); }
  }, [id]);
  useEffect(() => { if (user) load(); }, [user, load]);

  // light polling so the tracker updates without the customer refreshing or phoning support
  useEffect(() => {
    if (!user) return;
    const h = setInterval(() => { if (document.visibilityState === "visible") load(); }, 15000);
    return () => clearInterval(h);
  }, [user, load]);

  const next = order?.tracker.next_action?.type;
  useEffect(() => {
    if (next === "schedule") api<{ slots: Slot[] }>(`/orders/${id}/slots`).then((r) => setSlots(r.slots)).catch(() => {});
  }, [next, id]);

  async function book() {
    if (!pick) return;
    setBusy(true); setErr("");
    try { setOrder(await api<Order>(`/orders/${id}/schedule`, { body: pick })); setPick(null); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not book the slot"); }
    finally { setBusy(false); }
  }

  if (authLoading) return <Loading />;
  if (!user) return <div className="mx-auto max-w-xl px-4 py-12"><Empty title="Sign in to view this order"><Link href={`/login?next=/orders/${id}`} className="text-brand underline">Sign in</Link></Empty></div>;
  if (err && !order) return <div className="mx-auto max-w-xl px-4 py-12"><ErrorBox onRetry={load}>{err}</ErrorBox></div>;
  if (!order) return <Loading />;
  const na = order.tracker.next_action;

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">Order</p>
          <h1 className="font-mono text-2xl font-bold">{order.id}</h1>
          <p className="text-sm text-muted">{order.business_name} · placed {fmtDate(order.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={statusTone(order.status)}>{titleCase(order.status)}</Badge>
          <Badge tone={statusTone(order.payment_status)}>Payment: {titleCase(order.payment_status)}</Badge>
          <Badge tone={statusTone(order.kyc_status)}>KYC: {titleCase(order.kyc_status)}</Badge>
        </div>
      </div>

      <Card><Tracker steps={order.tracker.steps} /></Card>

      {na && (
        <Card className={cx(na.type !== "wait" && "border-brand bg-brand-soft")}>
          <p className="font-semibold">{na.type === "wait" ? "What's happening" : "Your next step"}</p>
          <p className="mt-1 text-sm">{na.message}</p>
          {(na.type === "kyc" || na.type === "kyc_fix") && <Link href={`/orders/${order.id}/kyc`} className="mt-3 inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white">{na.type === "kyc" ? "Start KYC" : "Fix documents"}</Link>}
          {na.type === "pay" && (
            <div className="mt-3 flex flex-wrap gap-2">
              {(["upi", "card", "netbanking"] as const).map((m) => (
                <Button key={m} variant="secondary" loading={busy} onClick={async () => {
                  setBusy(true); setErr("");
                  try { setOrder(await api<Order>(`/orders/${id}/pay`, { body: { method: m } })); }
                  catch (e) { setErr(e instanceof ApiError ? e.message : "Payment failed"); }
                  finally { setBusy(false); }
                }}>Pay {rupees(order.monthly_total + order.setup_total, true)} via {m === "netbanking" ? "net banking" : m.toUpperCase()} (simulated)</Button>
              ))}
            </div>
          )}
          {na.type === "schedule" && (
            <div className="mt-3 space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                {slots.slice(0, 10).map((s) => (
                  <div key={s.date} className="rounded-lg border border-line bg-white p-2 text-center">
                    <p className="text-xs text-muted">{s.weekday.slice(0, 3)}</p>
                    <p className="text-sm font-semibold">{fmtDate(s.date)}</p>
                    <div className="mt-1 flex flex-col gap-1">
                      {s.windows.map((w) => (
                        <button key={w.id} onClick={() => setPick({ date: s.date, window: w.id })} aria-pressed={pick?.date === s.date && pick.window === w.id}
                          className={cx("min-h-9 rounded border px-1 text-[11px]", pick?.date === s.date && pick.window === w.id ? "border-brand bg-brand text-white" : "border-line hover:border-brand")}>{w.label}</button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <Button onClick={book} disabled={!pick} loading={busy}>Book this slot</Button>
            </div>
          )}
        </Card>
      )}
      {err && <ErrorBox>{err}</ErrorBox>}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <p className="font-semibold">Delivery</p>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Installation visit</dt><dd>{order.install_slot ? `${fmtDate(order.install_slot.date)}, ${order.install_slot.window_label}` : "Not booked yet"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Expected activation</dt><dd>{order.activated_on ? `Live since ${fmtDate(order.activated_on)}` : order.expected_activation ? fmtDate(order.expected_activation) : `~${order.typical_install_days} days after KYC`}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Contract</dt><dd>{order.term_months} months</dd></div>
          </dl>
        </Card>
        <Card>
          <p className="font-semibold">Charges</p>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Monthly (incl. GST)</dt><dd>{rupees(order.monthly_total, true)}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">One-time setup (incl. GST)</dt><dd>{rupees(order.setup_total, true)}</dd></div>
          </dl>
          {order.items && <ul className="mt-3 border-t border-line pt-2 text-xs text-muted">{order.items.map((i) => <li key={i.product_id}>{i.quantity} × {i.name}</li>)}</ul>}
        </Card>
      </div>

      <Card>
        <p className="font-semibold">Activity</p>
        <ol className="mt-3 space-y-3 border-l-2 border-line pl-4">
          {[...order.events].reverse().map((e, i) => (
            <li key={i} className="relative text-sm">
              <span aria-hidden className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand" />
              <p className="font-medium">{titleCase(e.status)} <span className="text-xs font-normal text-muted">· {fmtDateTime(e.at)} · {e.actor}</span></p>
              {e.note && <p className="text-muted">{e.note}</p>}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
