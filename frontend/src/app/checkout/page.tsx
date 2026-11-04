"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order, SavedQuote } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Loading, cx } from "@/components/ui";

function Checkout() {
  const router = useRouter();
  const qid = useSearchParams().get("quote");
  const { user, loading: authLoading } = useAuth();
  const [quote, setQuote] = useState<SavedQuote | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [accept, setAccept] = useState(false);
  const [method, setMethod] = useState<"upi" | "card" | "netbanking">("upi");
  const [simFail, setSimFail] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!qid) { setLoading(false); return; }
    api<SavedQuote>(`/quotes/${qid}`).then(setQuote).catch((e: ApiError) => setErr(e.message)).finally(() => setLoading(false));
  }, [qid]);

  async function place() {
    if (!quote) return;
    setBusy(true); setErr("");
    try { setOrder(await api<Order>("/orders", { body: { quote_id: quote.id, accept_terms: accept } })); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not place the order"); }
    finally { setBusy(false); }
  }
  async function pay() {
    if (!order) return;
    setBusy(true); setErr("");
    try {
      const o = await api<Order>(`/orders/${order.id}/pay`, { body: { method, simulate: simFail ? "fail" : "success" } });
      setOrder(o);
      if (o.payment_status === "paid") router.push(`/orders/${o.id}/kyc`);
      else setErr("The simulated payment failed - this is how a declined payment looks. Untick 'simulate failure' and retry.");
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Payment failed"); }
    finally { setBusy(false); }
  }

  if (loading || authLoading) return <Loading />;
  if (!qid || !quote) return <div className="mx-auto max-w-xl px-4 py-12">{err ? <ErrorBox>{err}</ErrorBox> : <Empty title="No quote to check out"><Link href="/bundle" className="text-brand underline">Build your bundle</Link></Empty>}</div>;
  const t = quote.totals;

  return (
    <div className="mx-auto grid max-w-5xl gap-5 px-4 py-6 md:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Quote &amp; checkout</h1>
        <Card className="!p-0 overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="bg-neutral-50 text-left text-xs uppercase text-muted">
              <tr><th className="px-4 py-2">Product</th><th className="px-2 py-2 text-right">Qty</th><th className="px-2 py-2 text-right">Unit/mo</th><th className="px-2 py-2 text-right">Monthly</th><th className="px-4 py-2 text-right">Setup</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {quote.items.map((l) => (
                <tr key={l.product_id}>
                  <td className="px-4 py-3"><p className="font-medium">{l.name}</p><p className="text-xs text-muted">{l.unit} · {l.min_contract_months}-mo min · ~{l.install_days}d install</p></td>
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
          <p className="font-semibold">Contract &amp; terms</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
            <li>{t.term_months}-month contract; billed monthly after activation.</li>
            <li>Estimated activation about {t.install_days} days after KYC, based on the longest product lead time.</li>
            <li>{t.gst_note}</li>
            <li>Payment here is a simulation - no real money is charged.</li>
          </ul>
        </Card>
      </div>

      <aside className="md:sticky md:top-20 md:self-start">
        <Card className="space-y-3">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt>Monthly (excl. GST)</dt><dd>{rupees(t.monthly_subtotal, true)}</dd></div>
            <div className="flex justify-between text-muted"><dt>GST {t.gst_rate_percent}%</dt><dd>{rupees(t.monthly_gst, true)}</dd></div>
            <div className="flex justify-between border-t border-line pt-2 font-bold"><dt>Monthly recurring</dt><dd>{rupees(t.monthly_total, true)}</dd></div>
            <div className="flex justify-between pt-1"><dt>One-time setup (incl. GST)</dt><dd>{rupees(t.setup_total, true)}</dd></div>
            <div className="flex justify-between text-lg font-bold text-brand"><dt>Due today</dt><dd>{rupees(t.first_payment, true)}</dd></div>
            <div className="flex justify-between text-xs text-muted"><dt>Total over {t.term_months} months</dt><dd>{rupees(t.contract_value, true)}</dd></div>
          </dl>

          {!order && !user && (
            <div className="rounded-lg bg-brand-soft p-3 text-sm">
              <p className="font-medium">Sign in to place your order</p>
              <div className="mt-2 flex gap-2">
                <Link className="rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-white" href={`/register?next=${encodeURIComponent(`/checkout?quote=${qid}`)}`}>Create account</Link>
                <Link className="rounded-lg border border-brand px-3 py-2 text-xs font-semibold text-brand" href={`/login?next=${encodeURIComponent(`/checkout?quote=${qid}`)}`}>Sign in</Link>
              </div>
            </div>
          )}

          {!order && user && (
            <>
              <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5 h-5 w-5 accent-[#e40000]" checked={accept} onChange={(e) => setAccept(e.target.checked)} /> I accept the contract terms and the {t.term_months}-month commitment.</label>
              <Button className="w-full" disabled={!accept} loading={busy} onClick={place}>Confirm order</Button>
            </>
          )}

          {order && (
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg bg-green-50 px-3 py-2 text-sm"><span>Order placed</span><b className="font-mono">{order.id}</b></div>
              <p className="text-sm font-semibold">Pay {rupees(t.first_payment, true)} <Badge tone="info">simulated</Badge></p>
              <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Payment method">
                {(["upi", "card", "netbanking"] as const).map((m) => (
                  <button key={m} role="radio" aria-checked={method === m} onClick={() => setMethod(m)} className={cx("min-h-11 rounded-lg border px-2 text-xs font-semibold uppercase", method === m ? "border-brand bg-brand-soft text-brand" : "border-line")}>{m === "netbanking" ? "Net banking" : m}</button>
                ))}
              </div>
              <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={simFail} onChange={(e) => setSimFail(e.target.checked)} /> Demo: simulate a failed payment</label>
              <Button className="w-full" loading={busy} onClick={pay}>Pay {rupees(t.first_payment, true)}</Button>
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
