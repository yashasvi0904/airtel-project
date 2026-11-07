"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading } from "@/components/ui";
import { useLang } from "@/lib/i18n";

/** The SANDBOX bank page. With a real gateway the customer lands on their actual bank's site instead. */
function BankPage() {
  const { tr } = useLang();
  const router = useRouter();
  const ref = useSearchParams().get("ref");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  async function act(outcome: "authorize" | "decline" | "abandon") {
    if (!ref) return;
    setBusy(outcome); setErr("");
    try {
      const r = await api<{ order_id: string; status: string }>(`/payments/sandbox/${ref}/bank`, { body: { outcome } });
      router.replace(`/orders/${r.order_id}/pay`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : tr("The bank page could not complete. Please go back and try again."));
      setBusy("");
    }
  }

  if (!ref) return <div className="mx-auto max-w-md px-4 py-12"><ErrorBox>{tr("This bank link is incomplete. Go back to your order and start the payment again.")}</ErrorBox></div>;
  return (
    <div className="mx-auto max-w-md px-4 py-10">
      <Card className="space-y-4">
        <div className="flex items-center justify-between"><p className="text-lg font-bold">{tr("Sandbox Bank")}</p><Badge tone="warn">{tr("Test page - not a real bank")}</Badge></div>
        <p className="text-sm text-muted">{tr("This stands in for your bank's net banking page. Choose what happens next:")}</p>
        <Button className="w-full" loading={busy === "authorize"} disabled={!!busy} onClick={() => act("authorize")}>{tr("Log in and authorise payment")}</Button>
        <Button className="w-full" variant="secondary" loading={busy === "decline"} disabled={!!busy} onClick={() => act("decline")}>{tr("Bank declines the transaction")}</Button>
        <Button className="w-full" variant="ghost" loading={busy === "abandon"} disabled={!!busy} onClick={() => act("abandon")}>{tr("Close the page without paying")}</Button>
        {err && <ErrorBox>{err}</ErrorBox>}
      </Card>
    </div>
  );
}

export default function Page() {
  return <Suspense fallback={<Loading />}><BankPage /></Suspense>;
}
