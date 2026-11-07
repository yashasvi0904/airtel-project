"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { useLang } from "./i18n";
import { tx } from "./tx";

/**
 * Voice for the advisor: speak instead of typing, and listen to replies.
 *
 * Listening picks the best method available, and always says WHY when it cannot work (a silent dead button was the old failure):
 *   1. the browser's own speech recognition (Chrome/Edge/Android: instant, live text while speaking);
 *   2. otherwise, or if that service fails (blocked, offline, language not supported): record a short clip and have the server turn it
 *      into text with the AI provider. The clip is sent for transcription and discarded, never stored; the customer is told once.
 * Both need a secure page (HTTPS or localhost) and microphone permission: browsers refuse the microphone on plain http://192.168.x.x.
 */
interface Recognition {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null; onspeechstart: (() => void) | null;
  start(): void; stop(): void; abort(): void;
}
type RecognitionCtor = new () => Recognition;
declare global { interface Window { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor } }

export type VoiceStatus = "idle" | "listening" | "processing";
export type VoiceProblem = "insecure" | "unsupported" | "blocked" | "no-mic" | "no-speech" | "offline" | "language" | "server" | "consent" | "failed" | null;
const CONSENT_KEY = "udyam.voice.consent";
const MAX_RECORD_MS = 25_000;

const recognitionCtor = (): RecognitionCtor | undefined => (typeof window === "undefined" ? undefined : window.SpeechRecognition ?? window.webkitSpeechRecognition);
const canRecord = () => typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
const pickMime = () => ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((m) => MediaRecorder.isTypeSupported(m)) ?? "";

export function useVoice(locale: string, journeyId: string | null) {
  const { tn } = useLang();
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [problem, setProblem] = useState<VoiceProblem>(null);
  const [canSpeak, setCanSpeak] = useState(false);
  const [available, setAvailable] = useState(false); // false = hide the mic entirely (nothing could ever work in this browser)
  const [recordable, setRecordable] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const media = useRef<{ recorder: MediaRecorder; stream: MediaStream; timer: ReturnType<typeof setTimeout> } | null>(null);

  useEffect(() => {
    const secure = window.isSecureContext;
    setRecordable(secure && canRecord());
    setAvailable(!!recognitionCtor() || canRecord() || !secure); // when insecure we still show the mic, so tapping it can explain
    if (!("speechSynthesis" in window)) { setCanSpeak(false); return; }
    const check = () => setCanSpeak(window.speechSynthesis.getVoices().some((v) => v.lang.toLowerCase().startsWith(locale.slice(0, 2).toLowerCase())));
    check();
    window.speechSynthesis.addEventListener?.("voiceschanged", check); // voices load asynchronously on most phones
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", check);
  }, [locale]);

  const cleanup = useCallback(() => {
    rec.current?.abort(); rec.current = null;
    if (media.current) { clearTimeout(media.current.timer); media.current.stream.getTracks().forEach((t) => t.stop()); media.current = null; }
  }, []);
  useEffect(() => () => { cleanup(); if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }, [cleanup]);

  const stop = useCallback(() => {
    rec.current?.stop();
    if (media.current && media.current.recorder.state !== "inactive") media.current.recorder.stop();
  }, []);

  // ---- method 2: record a clip, let the server transcribe it
  const recordAndTranscribe = useCallback(async (onText: (t: string) => void) => {
    if (!journeyId) { setProblem("failed"); return; }
    if (localStorage.getItem(CONSENT_KEY) !== "yes") {
      // DPDP: tell the customer plainly what happens to their voice before sending it anywhere
      if (!window.confirm(tn("To turn your voice into text, a short recording is sent securely to our AI provider and deleted right after. It is not stored. Continue?"))) { setProblem("consent"); return; }
      localStorage.setItem(CONSENT_KEY, "yes");
    }
    let stream: MediaStream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { setProblem((e as DOMException).name === "NotFoundError" ? "no-mic" : "blocked"); setStatus("idle"); return; }
    const mime = pickMime();
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = async () => {
      if (media.current) { clearTimeout(media.current.timer); media.current.stream.getTracks().forEach((t) => t.stop()); media.current = null; }
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      setStatus("processing");
      try {
        const fd = new FormData();
        fd.append("file", blob, "voice." + (blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm"));
        const r = await api<{ text: string }>(`/journeys/${journeyId}/advisor/transcribe`, { form: fd });
        if (r.text.trim()) { onText(r.text.trim()); setProblem(null); } else setProblem("no-speech");
      } catch (e) {
        setProblem(e instanceof ApiError && e.status === 501 ? "unsupported" : "server");
      } finally { setStatus("idle"); }
    };
    media.current = { recorder, stream, timer: setTimeout(() => recorder.state !== "inactive" && recorder.stop(), MAX_RECORD_MS) };
    recorder.start();
    setStatus("listening");
  }, [journeyId, tn]);

  // ---- method 1: the browser's own recognition
  const listen = useCallback((onText: (t: string) => void) => {
    setProblem(null);
    if (!window.isSecureContext) { setProblem("insecure"); return; }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel(); // do not hear ourselves
    const Ctor = recognitionCtor();
    if (!Ctor) {
      if (canRecord()) void recordAndTranscribe(onText); else setProblem("unsupported");
      return;
    }
    const r = new Ctor();
    r.lang = locale; r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
    let finalText = "", heard = false, failed: string | null = null;
    const startedAt = Date.now();
    r.onspeechstart = () => { heard = true; };
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) finalText += res[0].transcript + " "; else interim += res[0].transcript;
      }
      heard = true;
      onText((finalText + interim).trim()); // live text while they speak
    };
    r.onerror = (e) => { failed = e.error; };
    r.onend = () => {
      rec.current = null;
      setStatus("idle");
      if (!failed || failed === "aborted") {
        if (heard || failed) return;
        // ended at once with no sound and no error: this browser's speech service is not really there (Brave, Chromium builds, some Android browsers).
        // Do not tell the customer they were silent - switch to recording a clip instead.
        if (Date.now() - startedAt < 3000 && canRecord()) void recordAndTranscribe(onText); else setProblem("no-speech");
        return;
      }
      if (failed === "no-speech") setProblem("no-speech");
      else if (failed === "not-allowed") setProblem("blocked");
      else if (failed === "audio-capture") setProblem("no-mic");
      else if (failed === "service-not-allowed" || failed === "network" || failed === "language-not-supported") {
        // the browser's speech service is unavailable here: use the recording route instead of leaving the customer stuck
        if (canRecord()) void recordAndTranscribe(onText); else setProblem(failed === "network" ? "offline" : failed === "language-not-supported" ? "language" : "blocked");
      } else setProblem("failed");
    };
    rec.current = r;
    setStatus("listening");
    try { r.start(); } catch { setStatus("idle"); setProblem("failed"); }
  }, [locale, recordAndTranscribe]);

  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/\*\*/g, "").replace(/[•]/g, ""));
    u.lang = locale;
    window.speechSynthesis.speak(u);
  }, [locale]);

  /** The explicit escape hatch: skip the browser's recognition and record a clip for the server to transcribe. */
  const recordInstead = useCallback((onText: (t: string) => void) => { setProblem(null); void recordAndTranscribe(onText); }, [recordAndTranscribe]);
  return { status, listening: status === "listening", processing: status === "processing", problem, clearProblem: () => setProblem(null), available, canRecordInstead: recordable && !!journeyId, canSpeak, listen, stop, speak, recordInstead };
}

/** The sentence shown to the customer for each reason voice did not work (translated by the page). */
export const VOICE_PROBLEM_TEXT: Record<Exclude<VoiceProblem, null>, string> = {
  insecure: tx("Voice needs a secure connection (https). On this address the browser blocks the microphone - please type your answer."),
  unsupported: tx("Voice is not available in this browser. Please type your answer."),
  blocked: tx("The microphone is blocked. Allow it in your browser's site settings, then tap the mic again."),
  "no-mic": tx("No microphone was found on this device."),
  "no-speech": tx("I did not hear anything. Tap the mic and speak again."),
  offline: tx("Voice recognition needs an internet connection."),
  language: tx("This browser cannot recognise your language by voice yet. Please type your answer."),
  server: tx("We could not turn that recording into text right now. Please try again or type your answer."),
  consent: tx("Voice was cancelled. You can type your answer instead."),
  failed: tx("Voice did not work this time. Please try again or type your answer."),
};
