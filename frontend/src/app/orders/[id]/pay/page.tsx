"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Card, Empty, ErrorBox, Loading } from "@/components/ui";
import PaymentPanel from "@/components/PaymentPanel";
import { useLang } from "@/lib/i18n";

export default function PayPage() {
  const { tr } = useLang();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!user) return;
    // a paid order still renders the panel: it shows the "payment received" confirmation + receipt, then moves on to KYC
    api<Order>(`/orders/${id}`).then(setOrder).catch((e: ApiError) => setErr(e.message));
  }, [id, user]);

  if (authLoading) return <Loading />;
  if (!user) {
    return <div className="mx-auto max-w-xl px-4 py-12"><Empty title={tr("Sign in to pay for your order")}><Link href={`/login?next=/orders/${id}/pay`} className="mt-2 inline-block rounded-lg bg-brand px-5 py-3 font-semibold text-white">Sign in</Link></Empty></div>;
  }
  if (err) return <div className="mx-auto max-w-xl px-4 py-12"><ErrorBox>{err}</ErrorBox></div>;
  if (!order) return <Loading />;
  const t = order.totals;
  const due = t ? t.first_payment : Math.round((order.monthly_total + order.setup_total) * 100) / 100;

  return (
    <div className="mx-auto grid max-w-4xl gap-5 px-4 py-6 md:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">{tr("Order")} <span className="font-mono">{order.id}</span></p>
          <h1 className="text-2xl font-bold">{tr("Complete your payment")}</h1>
          <p className="text-sm text-muted">{order.business_name}</p>
        </div>
        <Card><PaymentPanel orderId={order.id} amount={due} onPaid={() => router.replace(`/orders/${order.id}/kyc`)} /></Card>
        <p className="text-xs text-muted">{tr("Today you pay the first month and any one-time setup. Monthly billing continues after your services are activated, as per your contract.")}</p>
      </div>
      <aside className="md:sticky md:top-20 md:self-start">
        <Card className="space-y-2 text-sm">
          <p className="font-semibold">{tr("Order summary")}</p>
          {order.items?.map((l) => <div key={l.product_id} className="flex justify-between gap-2"><span>{l.name} × {l.quantity}</span><span>{rupees(l.monthly, true)}</span></div>)}
          {t && <>
            <div className="flex justify-between border-t border-line pt-2 text-muted"><span>{tr("Monthly (incl. GST)")}</span><span>{rupees(t.monthly_total, true)}</span></div>
            <div className="flex justify-between text-muted"><span>{tr("One-time setup (incl. GST)")}</span><span>{rupees(t.setup_total, true)}</span></div>
          </>}
          <div className="flex justify-between border-t border-line pt-2 text-base font-bold text-brand"><span>{tr("Due today")}</span><span>{rupees(due, true)}</span></div>
          <Link href={`/orders/${order.id}`} className="flex min-h-11 items-center text-sm text-brand underline">{tr("Back to order")}</Link>
        </Card>
      </aside>
    </div>
  );
}
