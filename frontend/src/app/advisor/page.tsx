"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, journeyStore } from "@/lib/api";
import type { AdvisorReply, Journey } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Loading, inputCls } from "@/components/ui";

interface Msg { role: "user" | "assistant"; content: string }

// Minimal **bold** renderer so the advisor's emphasis shows without a markdown dependency
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <p key={i} className={line.trim() === "" ? "h-2" : "leading-relaxed"}>
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => (part.startsWith("**") ? <b key={j}>{part.slice(2, -2)}</b> : <span key={j}>{part}</span>))}
        </p>
      ))}
    </>
  );
}

export default function AdvisorPage() {
  const [jid, setJid] = useState<string | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState<AdvisorReply["summary"] | null>(null);
  const [provider, setProvider] = useState("mock");
  const bottom = useRef<HTMLDivElement>(null);

  const init = useCallback(async () => {
    const id = journeyStore.get();
    setJid(id);
    if (!id) { setLoading(false); return; }
    setLoading(true);
    setErr("");
    try {
      const j = await api<Journey>(`/journeys/${id}`);
      setJourney(j);
      const s = await api<{ messages: Msg[]; chips?: string[]; provider: string; resumed: boolean }>(`/journeys/${id}/advisor/start`, { method: "POST" });
      setMsgs(s.messages);
      setChips(s.chips ?? []);
      setProvider(s.provider);
      if (j.stage === "recommended" || j.stage === "selected" || j.stage === "quoted") setReady({ tier: j.selection?.tier ?? "recommended", monthly_total: 0, setup_total: 0, items: j.selection?.items.length ?? 0 });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) { journeyStore.set(null); setJid(null); }
      else setErr(e instanceof ApiError ? e.message : "Could not load your session.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { init(); }, [init]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  async function send(value: string) {
    const v = value.trim();
    if (!v || busy || !jid) return;
    setText("");
    setErr("");
    setChips([]);
    setMsgs((m) => [...m, { role: "user", content: v }]);
    setBusy(true);
    try {
      const r = await api<AdvisorReply>(`/journeys/${jid}/advisor/message`, { body: { text: v } });
      setMsgs((m) => [...m, { role: "assistant", content: r.reply }]);
      setChips(r.chips);
      setProvider(r.provider);
      if (r.recommendation_ready) setReady(r.summary ?? { tier: "recommended", monthly_total: 0, setup_total: 0, items: 0 });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "The advisor could not answer. Please try again.");
      setMsgs((m) => m.slice(0, -1));
      setText(v);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading label="Starting your advisor..." />;
  if (!jid) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <Empty title="Let's start with your business">
          <p>The advisor needs a few details first.</p>
          <Link href="/onboarding" className="mt-4 inline-block rounded-lg bg-brand px-5 py-3 font-semibold text-white">Tell us about your business</Link>
        </Empty>
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-4 px-4 py-6 lg:grid-cols-[1fr_320px]">
      <Card className="flex h-[70vh] min-h-[420px] flex-col !p-0">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div>
            <p className="font-semibold">Your business advisor</p>
            <p className="text-xs text-muted">Ask in English, Hindi or Hinglish</p>
          </div>
          <Badge tone={provider === "anthropic" ? "info" : "neutral"}>{provider === "anthropic" ? "Claude AI" : "Offline rules mode"}</Badge>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
          {msgs.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm sm:max-w-[80%] ${m.role === "user" ? "rounded-br-sm bg-brand text-white" : "rounded-bl-sm bg-neutral-100"}`}>
                <RichText text={m.content} />
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex justify-start" aria-label="Advisor is typing">
              <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-neutral-100 px-4 py-4"><span className="dot h-2 w-2 rounded-full bg-neutral-500" /><span className="dot h-2 w-2 rounded-full bg-neutral-500" /><span className="dot h-2 w-2 rounded-full bg-neutral-500" /></div>
            </div>
          )}
          <div ref={bottom} />
        </div>
        {err && <div className="px-4 pb-2"><ErrorBox>{err}</ErrorBox></div>}
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pb-2">
            {chips.map((c) => <button key={c} onClick={() => send(c)} disabled={busy} className="min-h-9 rounded-full border border-brand/40 px-3 py-1 text-xs font-medium text-brand hover:bg-brand-soft disabled:opacity-50">{c}</button>)}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2 border-t border-line p-3">
          <input aria-label="Message" className={inputCls} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer..." maxLength={1000} disabled={busy} />
          <Button type="submit" disabled={!text.trim()} loading={busy}>Send</Button>
        </form>
      </Card>

      <aside className="space-y-4">
        {journey && (
          <Card>
            <p className="text-sm font-semibold">{journey.profile.business_name}</p>
            <p className="text-xs text-muted">{journey.profile.business_type} · {journey.profile.city} (tier {journey.profile.city_tier})</p>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-neutral-50 p-2"><dt className="text-muted">People</dt><dd className="text-base font-bold">{journey.profile.employees}</dd></div>
              <div className="rounded-lg bg-neutral-50 p-2"><dt className="text-muted">Sites</dt><dd className="text-base font-bold">{journey.profile.sites}</dd></div>
              <div className="rounded-lg bg-neutral-50 p-2"><dt className="text-muted">Budget</dt><dd className="text-base font-bold">{journey.profile.monthly_budget ? rupees(journey.profile.monthly_budget) : "-"}</dd></div>
            </dl>
            <p className="mt-3 text-xs text-muted">Segment: <b className="text-ink">{journey.profile.segment}</b></p>
            <p className="mt-1 text-xs text-muted">GSTIN: <b className="text-ink">{journey.profile.gstin_status === "active" ? "Active ✓" : journey.profile.gstin_status === "none" ? "Not added" : journey.profile.gstin_status}</b></p>
          </Card>
        )}
        <Card className={ready ? "border-brand" : ""}>
          <p className="font-semibold">{ready ? "Your bundle is ready" : "Recommendation"}</p>
          {ready ? (
            <>
              <p className="mt-1 text-sm text-muted">{ready.monthly_total ? `${rupees(ready.monthly_total, true)}/month incl. GST · ${ready.items} products` : "Review, customise and get a quote."}</p>
              <Link href="/bundle" className="mt-3 flex min-h-11 items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">Review &amp; customise bundle →</Link>
            </>
          ) : (
            <>
              <p className="mt-1 text-sm text-muted">Answer a few questions and I will build your bundle. Or skip ahead:</p>
              <Button variant="secondary" className="mt-3 w-full" onClick={() => send("recommend")} disabled={busy}>Recommend now</Button>
            </>
          )}
        </Card>
      </aside>
    </div>
  );
}
