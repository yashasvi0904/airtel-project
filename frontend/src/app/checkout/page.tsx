"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order, SavedQuote } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import { useLang } from "@/lib/i18n";

function Checkout() {
  const { tr, lm } = useLang();
  const router = useRouter();
  const qid = useSearchParams().get("quote");
  const { user, loading: authLoading } = useAuth();
  const [quote, setQuote] = useState<SavedQuote | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!qid) { setLoading(false); return; }
    api<SavedQuote>(`/quotes/${qid}`).then(setQuote).catch((e: ApiError) => setErr(e.message)).finally(() => setLoading(false));
  }, [qid]);

  async function place() {
    if (!quote) return;
    setBusy(true); setErr("");
    try {
      const o = await api<Order>("/orders", { body: { quote_id: quote.id, accept_terms: accept } });
      setOrder(o);
      router.push(o.payment_status === "paid" ? `/orders/${o.id}/kyc` : `/orders/${o.id}/pay`);
    }
    catch (e) { setErr(e instanceof ApiError ? e.message : tr("Could not place the order")); }
    finally { setBusy(false); }
  }
  if (loading || authLoading) return <Loading />;
  if (!qid || !quote) return <div className="mx-auto max-w-xl px-4 py-12">{err ? <ErrorBox>{err}</ErrorBox> : <Empty title={tr("No quote to check out")}><Link href="/bundle" className="text-brand underline">{tr("Build your bundle")}</Link></Empty>}</div>;
  const t = quote.totals;

  return (
    <div className="mx-auto grid max-w-5xl gap-5 px-4 py-6 md:grid-cols-[1fr_340px]">
      <div className="min-w-0 space-y-4">
        <h1 className="text-2xl font-bold">{tr("Quote & checkout")}</h1>
        <Card className="!p-0 overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="bg-neutral-50 text-left text-xs uppercase text-muted">
              <tr><th className="px-4 py-2">{tr("Product")}</th><th className="px-2 py-2 text-right">{tr("Qty")}</th><th className="px-2 py-2 text-right">{tr("Unit/mo")}</th><th className="px-2 py-2 text-right">{tr("Monthly")}</th><th className="px-4 py-2 text-right">{tr("Setup")}</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {quote.items.map((l) => (
                <tr key={l.product_id}>
                  <td className="px-4 py-3"><p className="font-medium">{l.name}</p><p className="text-xs text-muted">{tr("{unit} · {months}-month minimum · about {days} days to install", { unit: tr(l.unit), months: l.min_contract_months, days: l.install_days })}</p></td>
                  <td className="px-2 py-3 text-right">{l.quantity}</td>
                  <td className="px-2 py-3 text-right">{rupees(l.unit_price)}</td>
                  <td className="px-2 py-3 text-right">{rupees(l.monthly)}</td>
                  <td className="px-4 py-3 text-right">{l.setup ? rupees(l.setup) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card>
          <p className="font-semibold">{tr("Contract & terms")}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
            <li>{tr("{n}-month contract; billed monthly after activation.", { n: t.term_months })}</li>
            <li>{tr("Estimated activation about {n} days after KYC, based on the longest product lead time.", { n: t.install_days })}</li>
            <li>{lm(t.gst_note)}</li>
            <li>{tr("You pay the first month and the one-time setup today by UPI, card or net banking.")}</li>
          </ul>
        </Card>
      </div>

      <aside className="md:sticky md:top-20 md:self-start">
        <Card className="space-y-3">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt>{tr("Monthly (excl. GST)")}</dt><dd>{rupees(t.monthly_subtotal, true)}</dd></div>
            <div className="flex justify-between text-muted"><dt>{tr("GST {rate}%", { rate: t.gst_rate_percent })}</dt><dd>{rupees(t.monthly_gst, true)}</dd></div>
            <div className="flex justify-between border-t border-line pt-2 font-bold"><dt>{tr("Monthly recurring")}</dt><dd>{rupees(t.monthly_total, true)}</dd></div>
            <div className="flex justify-between pt-1"><dt>{tr("One-time setup (incl. GST)")}</dt><dd>{rupees(t.setup_total, true)}</dd></div>
            <div className="flex justify-between text-lg font-bold text-brand"><dt>{tr("Due today")}</dt><dd>{rupees(t.first_payment, true)}</dd></div>
            <div className="flex justify-between text-xs text-muted"><dt>{tr("Total over {n} months", { n: t.term_months })}</dt><dd>{rupees(t.contract_value, true)}</dd></div>
          </dl>

          {!order && !user && (
            <div className="rounded-lg bg-brand-soft p-3 text-sm">
              <p className="font-medium">{tr("Sign in to place your order")}</p>
              <div className="mt-2 flex gap-2">
                <Link className="rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-white" href={`/register?next=${encodeURIComponent(`/checkout?quote=${qid}`)}`}>{tr("Create account")}</Link>
                <Link className="rounded-lg border border-brand px-3 py-2 text-xs font-semibold text-brand" href={`/login?next=${encodeURIComponent(`/checkout?quote=${qid}`)}`}>{tr("Sign in")}</Link>
              </div>
            </div>
          )}

          {!order && user && (
            <>
              <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5 h-5 w-5 accent-[#e40000]" checked={accept} onChange={(e) => setAccept(e.target.checked)} /> {tr("I accept the contract terms and the {n}-month commitment.", { n: t.term_months })}</label>
              <Button className="w-full" disabled={!accept} loading={busy} onClick={place}>{tr("Confirm order")}</Button>
            </>
          )}

          {order && (
            <div className="space-y-2">
              <div className="flex items-center justify-between rounded-lg bg-green-50 px-3 py-2 text-sm"><span>{tr("Order placed")}</span><b className="font-mono">{order.id}</b></div>
              <Link href={`/orders/${order.id}/pay`} className="flex min-h-11 w-full items-center justify-center rounded-lg bg-brand px-5 font-semibold text-white">{tr("Continue to payment")}</Link>
            </div>
          )}
          {err && <ErrorBox>{err}</ErrorBox>}
        </Card>
      </aside>
    </div>
  );
}

export default function CheckoutPage() {
  return <Suspense fallback={<Loading />}><Checkout /></Suspense>;
}
