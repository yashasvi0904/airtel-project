"use client";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { NextAction, Payment, PaymentMethod, PaymentMethods } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Badge, Button, ErrorBox, Field, Loading, Spinner, cx, inputCls } from "@/components/ui";
import { failureText, nextActionText } from "@/lib/localizeMessage";
import { useLang } from "@/lib/i18n";

const VPA_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]{1,63}@[a-zA-Z][a-zA-Z0-9]{1,31}$/;
const POLL_MS = 2500;
const LIVE = ["created", "pending"];

function luhn(n: string) {
  if (!/^\d{12,19}$/.test(n)) return false;
  let sum = 0;
  [...n].reverse().forEach((ch, i) => { let d = Number(ch); if (i % 2 === 1) { d *= 2; if (d > 9) d -= 9; } sum += d; });
  return sum % 10 === 0;
}
const newKey = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().replace(/-/g, "") : Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join(""));
const groups = (digits: string) => digits.replace(/(\d{4})(?=\d)/g, "$1 ");

function useCountdown(iso: string | undefined) {
  const [left, setLeft] = useState(() => (iso ? Math.max(0, Math.floor((new Date(iso).getTime() - Date.now()) / 1000)) : 0));
  useEffect(() => {
    if (!iso) return;
    const tick = () => setLeft(Math.max(0, Math.floor((new Date(iso).getTime() - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [iso]);
  return `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
}

declare global { interface Window { Razorpay?: new (o: Record<string, unknown>) => { open(): void } } }

function loadRazorpay(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve();
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("load_failed"));
    document.body.appendChild(s);
  });
}

export default function PaymentPanel({ orderId, amount, onPaid }: { orderId: string; amount: number; onPaid: () => void }) {
  const { tr, tn } = useLang();
  const [cfg, setCfg] = useState<PaymentMethods | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("upi");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [loadErr, setLoadErr] = useState("");
  const [fe, setFe] = useState<Record<string, string>>({});
  // form state
  const [upiMode, setUpiMode] = useState<"collect" | "intent">("collect");
  const [vpa, setVpa] = useState("");
  const [bank, setBank] = useState("");
  const [card, setCard] = useState({ number: "", name: "", expiry: "", cvv: "" });
  const [otp, setOtp] = useState("");
  const keyRef = useRef<string | null>(null);
  const onPaidRef = useRef(onPaid);
  useEffect(() => { onPaidRef.current = onPaid; }, [onPaid]);

  // load config and resume an in-flight (or just-finished) attempt, e.g. after a refresh or coming back from the bank
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [c, list] = await Promise.all([api<PaymentMethods>("/payments/methods"), api<{ payments: Payment[]; order_payment_status: string }>(`/orders/${orderId}/payments`)]);
        if (!alive) return;
        setCfg(c);
        const latest = list.payments[0];
        const live = list.payments.find((p) => LIVE.includes(p.status));
        const paid = list.payments.find((p) => p.status === "succeeded");
        const recent = latest && Date.now() - new Date(latest.created_at).getTime() < 15 * 60_000;
        setPayment(live ?? paid ?? (recent && latest.status !== "cancelled" ? latest : null));
        if (live) setMethod(live.method);
      } catch (e) {
        if (alive) setLoadErr(e instanceof ApiError ? e.message : tn("Could not load payment options"));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [orderId, tn]);

  // poll while an attempt is live (UPI approvals, bank returns and webhooks all land here)
  const pid = payment?.id, pstatus = payment?.status, patype = payment?.next_action?.type;
  useEffect(() => {
    if (!pid || !pstatus || !LIVE.includes(pstatus) || patype === "redirect") return;
    const t = setInterval(async () => {
      try { setPayment(await api<Payment>(`/payments/${pid}`)); } catch { /* transient: next tick retries */ }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [pid, pstatus, patype]);

  useEffect(() => {
    if (pstatus !== "succeeded") return;
    const t = setTimeout(() => onPaidRef.current(), 2200);
    return () => clearTimeout(t);
  }, [pstatus]);

  // sandbox net banking: send the customer to the (sandbox) bank page
  useEffect(() => {
    if (payment?.status === "pending" && payment.next_action?.type === "redirect") {
      const url = payment.next_action.url;
      const t = setTimeout(() => window.location.assign(url), 900);
      return () => clearTimeout(t);
    }
  }, [payment]);

  function body(): Record<string, unknown> | null {
    const e: Record<string, string> = {};
    let out: Record<string, unknown> | null = null;
    if (method === "upi") {
      if (upiMode === "intent") out = { method, upi: { flow: "intent" } };
      else if (!VPA_RE.test(vpa.trim())) e.vpa = "Enter a valid UPI ID, like name@bank";
      else out = { method, upi: { flow: "collect", vpa: vpa.trim() } };
    } else if (method === "netbanking") {
      if (!bank) e.bank = tr("Choose your bank");
      else out = { method, netbanking: { bank } };
    } else if (cfg?.hosted_checkout) {
      out = { method }; // card details are typed into the gateway's own secure window, never into this page
    } else {
      const number = card.number.replace(/\s/g, "");
      const m = card.expiry.match(/^(\d{2})\/(\d{2})$/);
      const month = m ? Number(m[1]) : 0, year = m ? 2000 + Number(m[2]) : 0;
      const now = new Date();
      if (!luhn(number)) e.number = tr("That card number does not look right");
      if (!m || month < 1 || month > 12) e.expiry = tr("Use MM/YY");
      else if (year < now.getFullYear() || (year === now.getFullYear() && month < now.getMonth() + 1)) e.expiry = tr("This card has expired");
      if (!/^\d{3,4}$/.test(card.cvv)) e.cvv = "3 or 4 digits";
      if (!card.name.trim()) e.name = tr("Enter the name on the card");
      if (!Object.keys(e).length) out = { method, card: { number, name: card.name.trim(), exp_month: month, exp_year: year, cvv: card.cvv } };
    }
    setFe(e);
    return out;
  }

  async function start() {
    setErr("");
    const b = body();
    if (!b) return;
    setBusy(true);
    try {
      const p = await api<Payment>(`/orders/${orderId}/payments`, { body: b, headers: { "Idempotency-Key": (keyRef.current ??= newKey()) } });
      keyRef.current = null;
      setCard({ number: "", name: "", expiry: "", cvv: "" }); // the card number is not kept in the browser once sent
      setPayment(p);
      if (p.next_action?.type === "hosted_checkout") void openHosted(p);
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status !== 0) keyRef.current = null; // the server answered: a fresh submit is a fresh attempt. (status 0 = network: retry with the same key)
        const d = e.detail as { code?: string; payment_id?: string } | undefined;
        if (e.status === 409 && d?.code === "payment_in_progress" && d.payment_id) {
          try { setPayment(await api<Payment>(`/payments/${d.payment_id}`)); } catch { setErr(e.message); }
        } else if (e.status === 409 && d?.code === "already_paid") {
          onPaidRef.current();
        } else setErr(e.message);
      } else setErr(tr("Could not start the payment"));
    } finally { setBusy(false); }
  }

  async function cancel() {
    if (!payment) return;
    setBusy(true); setErr("");
    try { setPayment(await api<Payment>(`/payments/${payment.id}/cancel`, { method: "POST" })); setOtp(""); }
    catch (e) { setErr(e instanceof ApiError ? e.message : tr("Could not cancel")); try { setPayment(await api<Payment>(`/payments/${payment.id}`)); } catch { /* ignore */ } }
    finally { setBusy(false); }
  }

  async function sendOtp() {
    if (!payment) return;
    setBusy(true); setErr("");
    try { setPayment(await api<Payment>(`/payments/${payment.id}/otp`, { body: { otp } })); setOtp(""); }
    catch (e) {
      setErr(e instanceof ApiError ? e.message : tr("Could not verify the OTP"));
      setOtp("");
      try { setPayment(await api<Payment>(`/payments/${payment.id}`)); } catch { /* ignore */ }
    } finally { setBusy(false); }
  }

  async function openHosted(p: Payment) {
    const na = p.next_action;
    if (!na || na.type !== "hosted_checkout") return;
    setErr("");
    try {
      await loadRazorpay();
      const rz = new window.Razorpay!({
        key: na.key_id, order_id: na.gateway_order_id, amount: na.amount, currency: na.currency, name: na.name, description: na.description, prefill: na.prefill,
        handler: async (r: Record<string, string>) => {
          try { setPayment(await api<Payment>(`/payments/${p.id}/confirm`, { body: r })); }
          catch (e) { setErr(e instanceof ApiError ? e.message : tr("We could not confirm the payment yet. If money was deducted it will be matched to your order automatically.")); }
        },
        modal: { ondismiss: () => setErr(tr("The payment window was closed. You can reopen it, or cancel this attempt and choose another method.")) },
      });
      rz.open();
    } catch (e) { setErr(e instanceof Error && e.message === "load_failed" ? tr("Could not load the secure payment window. Check your connection.") : tr("Could not open the payment window")); }
  }

  if (loading) return <Loading label={tr("Loading payment options...")} />;
  if (loadErr || !cfg) return <ErrorBox>{loadErr || tr("Payment options are unavailable.")}</ErrorBox>;
  const sandbox = cfg.gateway === "sandbox";
  const live = payment && LIVE.includes(payment.status) ? payment : null;
  const done = payment?.status === "succeeded" ? payment : null;
  const failed = payment && ["failed", "expired"].includes(payment.status) ? payment : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-lg font-bold">{tr("Pay {amount}", { amount: rupees(amount, true) })}</p>
        {sandbox ? <Badge tone="warn">{tr("Sandbox - no real money")}</Badge> : <Badge tone="ok">{tr("Secure payment")}</Badge>}
      </div>

      {done && <Success p={done} />}
      {!done && live && <Pending p={live} busy={busy} otp={otp} setOtp={setOtp} onOtp={sendOtp} onCancel={cancel} onOpenHosted={() => void openHosted(live)} />}
      {!done && !live && (
        <>
          {failed && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"><b>{failed.status === "expired" ? tr("Payment timed out.") : tr("Payment failed.")}</b> {failureText(failed, tr)} {tr("No money was taken - you can retry below.")}</div>}
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={tr("Payment method")}>
            {cfg.methods.map((m) => (
              <button key={m.id} role="radio" aria-checked={method === m.id} onClick={() => { setMethod(m.id); setFe({}); setErr(""); }}
                className={cx("min-h-12 rounded-lg border px-2 text-sm font-semibold", method === m.id ? "border-brand bg-brand-soft text-brand" : "border-line hover:border-brand")}>
                {m.id === "card" ? tr("Card") : m.id === "netbanking" ? tr("Net banking") : "UPI"}
              </button>
            ))}
          </div>

          {method === "upi" && (
            <div className="space-y-3">
              <div className="flex gap-2 text-sm" role="radiogroup" aria-label={tr("UPI option")}>
                {([["collect", tr("Enter UPI ID")], ["intent", tr("Scan QR / open app")]] as const).map(([k, l]) => (
                  <button key={k} role="radio" aria-checked={upiMode === k} onClick={() => setUpiMode(k)} className={cx("min-h-11 rounded-full border px-4", upiMode === k ? "border-brand bg-brand-soft text-brand" : "border-line")}>{l}</button>
                ))}
              </div>
              {upiMode === "collect"
                ? <Field label={tr("UPI ID")} htmlFor="vpa" hint={tr("We will send a payment request to your UPI app (GPay, PhonePe, Paytm, BHIM...).")} error={fe.vpa}>
                    <input id="vpa" className={inputCls} value={vpa} onChange={(e) => setVpa(e.target.value)} placeholder={tr("yourname@okhdfc")} autoComplete="off" inputMode="email" autoCapitalize="none" spellCheck={false} />
                  </Field>
                : <p className="text-sm text-muted">{tr("We will show a QR code and a link that opens your UPI app with the amount filled in.")}</p>}
            </div>
          )}

          {method === "netbanking" && (
            <Field label={tr("Choose your bank")} htmlFor="bank" hint={tr("You will be taken to your bank's secure page to log in and approve.")} error={fe.bank}>
              <select id="bank" className={inputCls} value={bank} onChange={(e) => setBank(e.target.value)}>
                <option value="">{tr("Select bank")}</option>
                {cfg.banks.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
              </select>
            </Field>
          )}

          {method === "card" && (cfg.hosted_checkout
            ? <p className="text-sm text-muted">{tr("Your card details are entered in our payment partner's secure window. They never touch our servers.")}</p>
            : <div className="space-y-3">
                <Field label={tr("Card number")} htmlFor="cc" error={fe.number}>
                  <input id="cc" className={inputCls} value={card.number} onChange={(e) => setCard({ ...card, number: groups(e.target.value.replace(/\D/g, "").slice(0, 19)) })}
                    inputMode="numeric" autoComplete="cc-number" placeholder="1234 5678 9012 3456" />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={tr("Expiry")} htmlFor="exp" error={fe.expiry}>
                    <input id="exp" className={inputCls} value={card.expiry} inputMode="numeric" autoComplete="cc-exp" placeholder={tr("MM/YY")} maxLength={5}
                      onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 4); setCard({ ...card, expiry: d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d }); }} />
                  </Field>
                  <Field label={tr("CVV")} htmlFor="cvv" error={fe.cvv}>
                    <input id="cvv" type="password" className={inputCls} value={card.cvv} inputMode="numeric" autoComplete="cc-csc" placeholder="***" maxLength={4}
                      onChange={(e) => setCard({ ...card, cvv: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
                  </Field>
                </div>
                <Field label={tr("Name on card")} htmlFor="ccn" error={fe.name}>
                  <input id="ccn" className={inputCls} value={card.name} onChange={(e) => setCard({ ...card, name: e.target.value })} autoComplete="cc-name" />
                </Field>
              </div>)}

          {sandbox && cfg.sandbox_hints && (
            <details className="rounded-lg bg-neutral-50 p-3 text-xs text-muted">
              <summary className="flex min-h-11 cursor-pointer items-center font-semibold">{tr("Test details for this method (sandbox only)")}</summary>
              <ul className="mt-2 list-disc space-y-1 pl-4">{cfg.sandbox_hints[method].map((h) => <li key={h}>{h}</li>)}</ul>
            </details>
          )}
          <Button className="w-full" loading={busy} onClick={start}>
            {method === "upi" ? (upiMode === "intent" ? tr("Show QR code") : tr("Send payment request")) : method === "netbanking" ? tr("Continue to bank") : cfg.hosted_checkout ? tr("Open secure card window") : tr("Pay {amount}", { amount: rupees(amount, true) })}
          </Button>
          <p className="text-center text-xs text-muted">{tr("Valid for {n} minutes once started. Nothing is charged until you approve it.", { n: cfg.expiry_minutes })}</p>
        </>
      )}
      {err && <ErrorBox>{err}</ErrorBox>}
    </div>
  );
}

function Success({ p }: { p: Payment }) {
  const { tr } = useLang();
  return (
    <div role="status" className="space-y-1 rounded-lg border border-green-200 bg-green-50 px-4 py-4 text-sm text-green-900">
      <p className="text-base font-bold">{tr("Payment received - {amount}", { amount: rupees(p.amount, true) })}</p>
      <p>{p.method === "card" ? tr("Card") : p.method === "netbanking" ? tr("Net banking") : "UPI"} · {p.description}</p>
      <p className="text-xs">{tr("Receipt")} <span className="font-mono">{p.receipt}</span>. {tr("Taking you to the next step...")}</p>
    </div>
  );
}

function Pending({ p, busy, otp, setOtp, onOtp, onCancel, onOpenHosted }: { p: Payment; busy: boolean; otp: string; setOtp: (s: string) => void; onOtp: () => void; onCancel: () => void; onOpenHosted: () => void }) {
  const { tr } = useLang();
  const left = useCountdown(p.expires_at);
  const na = p.next_action as NextAction | null;
  return (
    <div className="space-y-3 rounded-lg border border-line bg-neutral-50 p-4" aria-live="polite">
      <div className="flex items-center gap-3">
        <Spinner />
        <div>
          <p className="text-sm font-semibold">{na?.type === "card_otp" ? tr("Verify with your bank") : na?.type === "hosted_checkout" ? tr("Complete the secure payment") : tr("Waiting for your approval")}</p>
          <p className="text-xs text-muted">{nextActionText(p, tr)} · {tr("expires in {time}", { time: left })}</p>
        </div>
      </div>
      {na?.type === "upi_intent" && <UpiQr url={na.intent_url} />}
      {na?.type === "card_otp" && (
        <div className="space-y-2">
          <Field label={tr("One-time password")} htmlFor="otp">
            <input id="otp" className={inputCls} value={otp} inputMode="numeric" autoComplete="one-time-code" maxLength={8} placeholder={tr("6-digit OTP")}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} onKeyDown={(e) => { if (e.key === "Enter" && otp.length >= 4) onOtp(); }} />
          </Field>
          <Button loading={busy} disabled={otp.length < 4} onClick={onOtp}>{tr("Verify and pay")}</Button>
        </div>
      )}
      {na?.type === "hosted_checkout" && <Button onClick={onOpenHosted}>{tr("Open payment window")}</Button>}
      {p.details.last_failure ? <p className="text-xs text-amber-800">{String(p.details.last_failure)}</p> : null}
      <button className="inline-flex min-h-11 items-center text-sm text-brand underline disabled:opacity-50" disabled={busy} onClick={onCancel}>{tr("Cancel and choose another method")}</button>
    </div>
  );
}

function UpiQr({ url }: { url: string }) {
  const { tr } = useLang();
  const [src, setSrc] = useState("");
  useEffect(() => { QRCode.toDataURL(url, { margin: 1, width: 220 }).then(setSrc).catch(() => setSrc("")); }, [url]);
  return (
    <div className="flex flex-col items-center gap-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src ? <img src={src} alt={tr("UPI QR code for this payment")} width={220} height={220} className="rounded-lg border border-line bg-white" /> : <Spinner />}
      <a href={url} className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 text-sm font-semibold text-white">{tr("Open UPI app")}</a>
      <p className="text-center text-xs text-muted">{tr("Scan with any UPI app, or tap the button on your phone. This page updates by itself when the payment goes through.")}</p>
    </div>
  );
}
