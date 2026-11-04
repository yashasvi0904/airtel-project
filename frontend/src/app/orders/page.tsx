"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { fmtDate, rupees, titleCase } from "@/lib/format";
import { Badge, Card, Empty, ErrorBox, Loading, statusTone } from "@/components/ui";

export default function OrdersPage() {
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
        <Empty title="Sign in to see your orders">
          <Link href="/login?next=/orders" className="mt-2 inline-block rounded-lg bg-brand px-5 py-3 font-semibold text-white">Sign in</Link>
        </Empty>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 py-8">
      <h1 className="text-2xl font-bold">My orders</h1>
      {err && <ErrorBox onRetry={load}>{err}</ErrorBox>}
      {!orders && !err && <Loading />}
      {orders && orders.length === 0 && <Empty title="No orders yet"><Link href="/onboarding" className="text-brand underline">Build your first plan</Link></Empty>}
      {orders?.map((o) => (
        <Link key={o.id} href={`/orders/${o.id}`} className="block">
          <Card className="transition hover:border-brand">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-mono text-sm font-semibold">{o.id}</p>
                <p className="text-sm text-muted">{o.business_name} · placed {fmtDate(o.created_at)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={statusTone(o.status)}>{titleCase(o.status)}</Badge>
                <Badge tone={statusTone(o.kyc_status)}>KYC: {titleCase(o.kyc_status)}</Badge>
                <Badge tone={statusTone(o.payment_status)}>Payment: {titleCase(o.payment_status)}</Badge>
              </div>
            </div>
            <p className="mt-3 text-sm">{rupees(o.monthly_total, true)}/month · {o.term_months} months{o.tracker.next_action && <span className="font-medium text-brand"> · {o.tracker.next_action.message}</span>}</p>
          </Card>
        </Link>
      ))}
    </div>
  );
}
