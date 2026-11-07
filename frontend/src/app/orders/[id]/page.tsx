"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order, Payment } from "@/lib/types";
import { fmtDate, fmtDateTime, rupees, titleCase } from "@/lib/format";
import Tracker from "@/components/Tracker";
import { Badge, Button, Card, Empty, ErrorBox, Loading, cx, statusTone } from "@/components/ui";
import { useLang } from "@/lib/i18n";
import { failureText, localizeMessage } from "@/lib/localizeMessage";

interface Slot { date: string; weekday: string; windows: { id: string; label: string }[] }

export default function OrderPage() {
  const { tr, lm, tn } = useLang();
  const { id } = useParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [err, setErr] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [pick, setPick] = useState<{ date: string; window: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setErr("");
    try {
      setOrder(await api<Order>(`/orders/${id}`));
      api<{ payments: Payment[] }>(`/orders/${id}/payments`).then((r) => setPayments(r.payments)).catch(() => {});
    }
    catch (e) { setErr(e instanceof ApiError ? (e.status === 404 ? tn("We could not find this order on your account.") : e.message) : tn("Could not load the order")); }
  }, [id, tn]);
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
    catch (e) { setErr(e instanceof ApiError ? e.message : tr("Could not book the slot")); }
    finally { setBusy(false); }
  }

  if (authLoading) return <Loading />;
  if (!user) return <div className="mx-auto max-w-xl px-4 py-12"><Empty title={tr("Sign in to view this order")}><Link href={`/login?next=/orders/${id}`} className="text-brand underline">{tr("Sign in")}</Link></Empty></div>;
  if (err && !order) return <div className="mx-auto max-w-xl px-4 py-12"><ErrorBox onRetry={load}>{err}</ErrorBox></div>;
  if (!order) return <Loading />;
  const na = order.tracker.next_action;

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">{tr("Order")}</p>
          <h1 className="font-mono text-2xl font-bold">{order.id}</h1>
          <p className="text-sm text-muted">{order.business_name} · {tr("placed {date}", { date: fmtDate(order.created_at) })}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={statusTone(order.status)}>{tr(titleCase(order.status))}</Badge>
          <Badge tone={statusTone(order.payment_status)}>{tr("Payment")}: {tr(titleCase(order.payment_status))}</Badge>
          <Badge tone={statusTone(order.kyc_status)}>KYC: {tr(titleCase(order.kyc_status))}</Badge>
        </div>
      </div>

      <Card><Tracker steps={order.tracker.steps} /></Card>

      {na && (
        <Card className={cx(na.type !== "wait" && "border-brand bg-brand-soft")}>
          <p className="font-semibold">{na.type === "wait" ? tr("What's happening") : tr("Your next step")}</p>
          <p className="mt-1 text-sm">{lm(na.message)}</p>
          {(na.type === "kyc" || na.type === "kyc_fix") && <Link href={`/orders/${order.id}/kyc`} className="mt-3 inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white">{na.type === "kyc" ? tr("Start KYC") : tr("Fix documents")}</Link>}
          {na.type === "pay" && (
            <Link href={`/orders/${order.id}/pay`} className="mt-3 inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white">
              {order.payment_status === "failed" ? tr("Try payment again") : order.payment_status === "processing" ? tr("Check payment status") : `Pay ${rupees(order.monthly_total + order.setup_total, true)}`}
            </Link>
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
              <Button onClick={book} disabled={!pick} loading={busy}>{tr("Book this slot")}</Button>
            </div>
          )}
        </Card>
      )}
      {err && <ErrorBox>{err}</ErrorBox>}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <p className="font-semibold">{tr("Delivery")}</p>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-muted">{tr("Installation visit")}</dt><dd>{order.install_slot ? `${fmtDate(order.install_slot.date)}, ${tr(order.install_slot.window_label)}` : tr("Not booked yet")}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">{tr("Expected activation")}</dt><dd>{order.activated_on ? tr("Live since {date}", { date: fmtDate(order.activated_on) }) : order.expected_activation ? fmtDate(order.expected_activation) : tr("~{n} days after KYC", { n: order.typical_install_days })}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">{tr("Contract")}</dt><dd>{tr("{n} months", { n: order.term_months })}</dd></div>
          </dl>
        </Card>
        <Card>
          <p className="font-semibold">{tr("Charges")}</p>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-muted">{tr("Monthly (incl. GST)")}</dt><dd>{rupees(order.monthly_total, true)}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">{tr("One-time setup (incl. GST)")}</dt><dd>{rupees(order.setup_total, true)}</dd></div>
          </dl>
          {order.items && <ul className="mt-3 border-t border-line pt-2 text-xs text-muted">{order.items.map((i) => <li key={i.product_id}>{i.quantity} × {i.name}</li>)}</ul>}
        </Card>
      </div>

      {payments.length > 0 && (
        <Card>
          <p className="font-semibold">{tr("Payments")}</p>
          <ul className="mt-2 divide-y divide-line text-sm">
            {payments.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div>
                  <p className="font-medium">{p.method_label} · {p.description}</p>
                  <p className="text-xs text-muted">{tr("Attempt {n}", { n: p.attempt_no })} · {fmtDateTime(p.created_at)} · {tr("receipt")} <span className="font-mono">{p.receipt}</span>{p.failure_message && p.status !== "succeeded" ? ` · ${failureText(p, tr)}` : ""}</p>
                </div>
                <div className="flex items-center gap-2"><span>{rupees(p.amount, true)}</span><Badge tone={statusTone(p.status)}>{tr(titleCase(p.status))}</Badge></div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <p className="font-semibold">{tr("Activity")}</p>
        <ol className="mt-3 space-y-3 border-l-2 border-line pl-4">
          {[...order.events].reverse().map((e, i) => (
            <li key={i} className="relative text-sm">
              <span aria-hidden className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand" />
              <p className="font-medium">{tr(titleCase(e.status))} <span className="text-xs font-normal text-muted">· {fmtDateTime(e.at)} · {tr(e.actor)}</span></p>
              {e.note && <p className="text-muted">{localizeMessage(e.note, tr)}</p>}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
