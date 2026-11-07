"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, journeyStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { fmtDate, rupees, titleCase } from "@/lib/format";
import { Badge, Card, Empty, ErrorBox, Loading, statusTone } from "@/components/ui";
import { useLang } from "@/lib/i18n";

export default function OrdersPage() {
  const { tr, lm } = useLang();
  const { user, loading: authLoading } = useAuth();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    setErr("");
    api<Order[]>("/orders").then(setOrders).catch((e: ApiError) => setErr(e.message));
  }, []);
  useEffect(() => { if (user) load(); }, [user, load]);

  if (authLoading) return <Loading />;
  if (!user) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <Empty title={tr("Sign in to see your orders")}>
          <Link href="/login?next=/orders" className="mt-2 inline-block rounded-lg bg-brand px-5 py-3 font-semibold text-white">{tr("Sign in")}</Link>
        </Empty>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{tr("My orders")}</h1>
        <Link
          href="/onboarding"
          onClick={() => journeyStore.set(null)}
          className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-3 font-semibold text-white transition hover:opacity-90"
        >
          <span aria-hidden="true" className="text-xl leading-none">+</span> New order
        </Link>
      </div>
      {err && <ErrorBox onRetry={load}>{err}</ErrorBox>}
      {!orders && !err && <Loading />}
      {orders && orders.length === 0 && <Empty title={tr("No orders yet")}><Link href="/onboarding" onClick={() => journeyStore.set(null)} className="text-brand underline">{tr("Build your first plan")}</Link></Empty>}
      {orders?.map((o) => (
        <Link key={o.id} href={`/orders/${o.id}`} className="block">
          <Card className="transition hover:border-brand">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-mono text-sm font-semibold">{o.id}</p>
                <p className="text-sm text-muted">{o.business_name} · {tr("placed {date}", { date: fmtDate(o.created_at) })}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={statusTone(o.status)}>{tr(titleCase(o.status))}</Badge>
                <Badge tone={statusTone(o.kyc_status)}>KYC: {tr(titleCase(o.kyc_status))}</Badge>
                <Badge tone={statusTone(o.payment_status)}>{tr("Payment")}: {tr(titleCase(o.payment_status))}</Badge>
              </div>
            </div>
            <p className="mt-3 text-sm">{tr("{amount}/month · {n} months", { amount: rupees(o.monthly_total, true), n: o.term_months })}{o.tracker.next_action && <span className="font-medium text-brand"> · {lm(o.tracker.next_action.message)}</span>}</p>
          </Card>
        </Link>
      ))}
    </div>
  );
}
