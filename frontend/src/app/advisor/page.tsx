"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, journeyStore } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { localeOf } from "@/lib/languages";
import { useVoice, VOICE_PROBLEM_TEXT } from "@/lib/speech";
import type { AdvisorReply, Journey } from "@/lib/types";
import { rupees } from "@/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Spinner, inputCls } from "@/components/ui";

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
  const { lang, tr, tn } = useLang();
  const [jid, setJid] = useState<string | null>(null);
  const speech = useVoice(localeOf(lang), jid);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState<AdvisorReply["summary"] | null>(null);
  const [provider, setProvider] = useState("mock");
  const [understood, setUnderstood] = useState<string[]>([]);
  const [progress, setProgress] = useState<{ asked: number; max: number } | null>(null);
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
      const s = await api<{ messages: Msg[]; chips?: string[]; provider: string; resumed: boolean; understood?: string[]; progress?: { asked: number; max: number } }>(`/journeys/${id}/advisor/start`, { method: "POST" });
      setMsgs(s.messages);
      setChips(s.chips ?? []);
      setProvider(s.provider);
      setUnderstood(s.understood ?? []);
      setProgress(s.progress ?? null);
      if (j.stage === "recommended" || j.stage === "selected" || j.stage === "quoted") setReady({ tier: j.selection?.tier ?? "recommended", monthly_total: 0, setup_total: 0, items: j.selection?.items.length ?? 0 });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) { journeyStore.set(null); setJid(null); }
      else setErr(e instanceof ApiError ? e.message : tn("Could not load your session."));
    } finally {
      setLoading(false);
    }
  }, [tn]);
  useEffect(() => { init(); }, [init]);
  // a resumed session opened in another language: the advisor continues in the language the screen is in now
  useEffect(() => {
    if (jid && journey && journey.language !== lang) api(`/journeys/${jid}/language`, { method: "PUT", body: { language: lang } }).then(() => setJourney((j) => (j ? { ...j, language: lang } : j))).catch(() => {});
  }, [jid, journey, lang]);
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
      setUnderstood(r.understood ?? []);
      setProgress(r.progress ?? null);
      if (r.recommendation_ready) setReady(r.summary ?? { tier: "recommended", monthly_total: 0, setup_total: 0, items: 0 });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : tr("The advisor could not answer. Please try again."));
      setMsgs((m) => m.slice(0, -1));
      setText(v);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading label={tr("Starting your advisor...")} />;
  if (!jid) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <Empty title={tr("Let's start with your business")}>
          <p>{tr("The advisor needs a few details first.")}</p>
          <Link href="/onboarding" className="mt-4 inline-block rounded-lg bg-brand px-5 py-3 font-semibold text-white">{tr("Tell us about your business")}</Link>
        </Empty>
      </div>
    );
  }

  return (
    <div className={`mx-auto grid max-w-6xl gap-4 px-4 py-4 lg:grid-cols-[1fr_320px] lg:py-6 ${ready ? "pb-24 lg:pb-6" : ""}`}>
      <Card className="flex h-[calc(100dvh-11rem)] min-h-[420px] flex-col !p-0 lg:h-[70vh]">
        <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            <p className="font-semibold">{tr("Your business advisor")}</p>
            <p className="text-xs text-muted">{tr("Ask in your own language - type or speak")}</p>
          </div>
          <span className="shrink-0 whitespace-nowrap"><Badge tone={provider === "anthropic" || provider === "gemini" ? "info" : "neutral"}>{provider === "anthropic" ? "Claude AI" : provider === "gemini" ? "Gemini AI" : tr("Offline rules mode")}</Badge></span>
        </div>
        {(understood.length > 0 || (progress && !ready)) && (
          <div className="border-b border-line bg-neutral-50 px-4 py-2" aria-label={tr("What I have understood so far")}>
            <div className="flex items-center justify-between gap-2 text-xs text-muted">
              <span className="font-semibold">{understood.length ? tr("I have noted:") : tr("Tell me what you need")}</span>
              {progress && !ready && <span>{tr("Question {n} of about {m}", { n: Math.min(progress.asked, progress.max), m: progress.max })}</span>}
            </div>
            {understood.length > 0 && (
              <ul className="mt-1 flex gap-1.5 overflow-x-auto pb-0.5">
                {understood.map((u) => <li key={u} className="shrink-0 rounded-full border border-brand/30 bg-white px-2.5 py-1 text-xs text-ink">{u}</li>)}
              </ul>
            )}
          </div>
        )}
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
          {msgs.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm sm:max-w-[80%] ${m.role === "user" ? "rounded-br-sm bg-brand text-white" : "rounded-bl-sm bg-neutral-100"}`}>
                <RichText text={m.content} />
                {m.role === "assistant" && speech.canSpeak && (
                  <button onClick={() => speech.speak(m.content)} aria-label={tr("Read aloud")} className="mt-1 inline-flex min-h-11 items-center gap-1 rounded-lg pr-2 text-xs font-medium text-brand">
                    <span aria-hidden="true">&#128266;</span> {tr("Listen")}
                  </button>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex justify-start" aria-label={tr("Advisor is typing")}>
              <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-neutral-100 px-4 py-4"><span className="dot h-2 w-2 rounded-full bg-neutral-500" /><span className="dot h-2 w-2 rounded-full bg-neutral-500" /><span className="dot h-2 w-2 rounded-full bg-neutral-500" /></div>
            </div>
          )}
          <div ref={bottom} />
        </div>
        {err && <div className="px-4 pb-2"><ErrorBox>{err}</ErrorBox></div>}
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pb-2">
            {chips.map((c) => <button key={c} onClick={() => send(c)} disabled={busy} className="min-h-11 rounded-full border border-brand/40 px-4 py-1 text-sm font-medium text-brand hover:bg-brand-soft disabled:opacity-50">{tr(c)}</button>)}
          </div>
        )}
        {speech.problem && (
          <div role="status" className="mx-3 mt-2 flex items-start justify-between gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <span>
              {tr(VOICE_PROBLEM_TEXT[speech.problem])}
              {speech.canRecordInstead && ["no-speech", "offline", "language", "failed", "server"].includes(speech.problem) && (
                <button type="button" onClick={() => speech.recordInstead((v) => setText(v))} className="ml-2 inline-flex min-h-11 items-center font-semibold text-brand underline">{tr("Record instead")}</button>
              )}
            </span>
            <button type="button" onClick={speech.clearProblem} aria-label={tr("Close")} className="grid h-8 w-8 shrink-0 place-items-center rounded text-base leading-none">&times;</button>
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); speech.stop(); send(text); }} className="flex gap-2 border-t border-line p-3">
          {speech.available && (
            <button type="button" disabled={speech.processing} onClick={() => (speech.listening ? speech.stop() : speech.listen((v) => setText(v)))} aria-pressed={speech.listening}
              aria-label={speech.listening ? tr("Stop listening") : tr("Speak your answer")}
              className={`grid h-11 w-11 shrink-0 place-items-center rounded-lg border text-lg ${speech.listening ? "animate-pulse border-brand bg-brand text-white" : "border-line hover:border-brand"}`}>
              {speech.processing ? <Spinner small /> : <span aria-hidden="true">&#127908;</span>}
            </button>
          )}
          <input aria-label={tr("Message")} className={inputCls} value={text} onChange={(e) => setText(e.target.value)} placeholder={speech.listening ? tr("Listening...") : speech.processing ? tr("Turning your voice into text...") : tr("Type your answer...")} maxLength={1000} disabled={busy}
            enterKeyHint="send" autoComplete="off" lang={lang} />
          <Button type="submit" disabled={!text.trim()} loading={busy}>{tr("Send")}</Button>
        </form>
      </Card>

      <aside className="space-y-4">
        {journey && (
          <Card>
            <p className="text-sm font-semibold">{journey.profile.business_name}</p>
            <p className="text-xs text-muted">{tr(journey.profile.business_type)} · {journey.profile.city} ({tr("tier {tier}", { tier: journey.profile.city_tier })})</p>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-neutral-50 p-2"><dt className="text-muted">{tr("People")}</dt><dd className="text-base font-bold">{journey.profile.employees}</dd></div>
              <div className="rounded-lg bg-neutral-50 p-2"><dt className="text-muted">{tr("Sites")}</dt><dd className="text-base font-bold">{journey.profile.sites}</dd></div>
              <div className="rounded-lg bg-neutral-50 p-2"><dt className="text-muted">{tr("Budget")}</dt><dd className="text-base font-bold">{journey.profile.monthly_budget ? rupees(journey.profile.monthly_budget) : "-"}</dd></div>
            </dl>
            <p className="mt-3 text-xs text-muted">{tr("Segment")}: <b className="text-ink">{tr(journey.profile.segment)}</b></p>
            <p className="mt-1 text-xs text-muted">GSTIN: <b className="text-ink">{journey.profile.gstin_status === "active" ? tr("Active") + " ✓" : journey.profile.gstin_status === "none" ? tr("Not added") : journey.profile.gstin_status}</b></p>
          </Card>
        )}
        <Card className={ready ? "border-brand" : ""}>
          <p className="font-semibold">{ready ? tr("Your bundle is ready") : tr("Recommendation")}</p>
          {ready ? (
            <>
              <p className="mt-1 text-sm text-muted">{ready.monthly_total ? tr("{amount}/month incl. GST · {n} products", { amount: rupees(ready.monthly_total, true), n: ready.items }) : tr("Review, customise and get a quote.")}</p>
              <Link href="/bundle" className="mt-3 flex min-h-11 items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">{tr("Review & customise bundle")} →</Link>
            </>
          ) : (
            <>
              <p className="mt-1 text-sm text-muted">{tr("Answer a few questions and I will build your bundle. Or skip ahead:")}</p>
              <Button variant="secondary" className="mt-3 w-full" onClick={() => send("recommend")} disabled={busy}>{tr("Recommend now")}</Button>
            </>
          )}
        </Card>
      </aside>
      {ready && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-white p-3 shadow-[0_-4px_12px_rgba(0,0,0,0.08)] lg:hidden">
          <Link href="/bundle" className="flex min-h-12 items-center justify-center rounded-lg bg-brand px-4 text-base font-semibold text-white">{tr("Review & customise bundle")} →</Link>
        </div>
      )}
    </div>
  );
}
