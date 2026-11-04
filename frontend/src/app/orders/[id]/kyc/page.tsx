"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { KycCase, KycReport } from "@/lib/types";
import { fmtDate, titleCase } from "@/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, cx, inputCls, statusTone } from "@/components/ui";

const DOC_HINT: Record<string, string> = {
  gst_certificate: "GST registration certificate (PNG/JPG)",
  udyam_certificate: "Udyam registration certificate",
  signatory_id: "Government-style ID of the authorised signatory",
  address_proof: "Electricity / utility bill dated within the last 90 days",
};
const STATUS_TEXT: Record<string, string> = {
  verified: "Verified", needs_review: "Needs a quick manual review", action_required: "Action required", incomplete: "Documents missing",
  rejected: "Could not be verified", awaiting_documents: "Awaiting documents", approved: "Approved after review",
};

export default function KycPage() {
  const { id } = useParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const [kyc, setKyc] = useState<KycCase | null>(null);
  const [err, setErr] = useState("");
  const [busyDoc, setBusyDoc] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [decl, setDecl] = useState({ has_gstin: true, has_udyam: true, gstin: "", udyam_number: "" });
  const [savingConsent, setSavingConsent] = useState(false);
  const [samples, setSamples] = useState<{ id: string; documents: string[] }[]>([]);
  const [sample, setSample] = useState("");
  const [progress, setProgress] = useState("");
  const [showChecks, setShowChecks] = useState(false);

  const load = useCallback(async () => {
    try { setKyc(await api<KycCase>(`/orders/${id}/kyc`)); setErr(""); }
    catch (e) { setErr(e instanceof ApiError ? (e.status === 404 ? "We could not find this order on your account." : e.message) : "Could not load KYC"); }
  }, [id]);
  useEffect(() => { if (user) { load(); api<{ applicants: { id: string; documents: string[] }[] }>("/demo/kyc-samples").then((r) => setSamples(r.applicants)).catch(() => {}); } }, [user, load]);

  async function giveConsent() {
    setSavingConsent(true); setErr("");
    try {
      const body = { accepted: consent, has_gstin: decl.has_gstin, has_udyam: decl.has_udyam, gstin: decl.gstin || null, udyam_number: decl.udyam_number || null };
      await api(`/orders/${id}/kyc/consent`, { body });
      await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not record consent"); }
    finally { setSavingConsent(false); }
  }

  async function uploadFile(docType: string, file: File | Blob, name: string) {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file, name);
    const r = await api<KycCase>(`/orders/${id}/kyc/documents`, { form });
    setKyc((k) => (k ? { ...k, ...r } : r));
  }

  async function onPick(docType: string, file: File | undefined) {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) return setErr("That file is larger than 8 MB. Please upload a smaller photo or scan.");
    if (!/^image\/(png|jpe?g)$/.test(file.type)) return setErr("Please upload a PNG or JPG image.");
    setBusyDoc(docType); setErr("");
    try { await uploadFile(docType, file, file.name); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Upload failed"); }
    finally { setBusyDoc(null); }
  }

  async function loadSample() {
    const app = samples.find((s) => s.id === sample);
    if (!app) return;
    setErr("");
    try {
      for (const doc of app.documents) {
        setProgress(`Uploading ${titleCase(doc)}...`);
        setBusyDoc(doc);
        const blob = await (await fetch(`/api/demo/kyc-samples/${app.id}/${doc}`)).blob();
        await uploadFile(doc, blob, `${app.id}_${doc}.png`);
      }
      await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not load the sample documents"); }
    finally { setBusyDoc(null); setProgress(""); }
  }

  async function erase() {
    if (!confirm("Delete all uploaded documents and extracted data for this order? You will need to upload them again to continue.")) return;
    try { await api(`/orders/${id}/kyc`, { method: "DELETE" }); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not delete"); }
  }

  if (authLoading) return <Loading />;
  if (!user) return <div className="mx-auto max-w-xl px-4 py-12"><Empty title="Sign in to continue"><Link href={`/login?next=/orders/${id}/kyc`} className="text-brand underline">Sign in</Link></Empty></div>;
  if (!kyc) return <div className="mx-auto max-w-xl px-4 py-12">{err ? <ErrorBox onRetry={load}>{err}</ErrorBox> : <Loading />}</div>;

  const res: KycReport | null = kyc.result;
  const hasConsent = !!kyc.consent;
  const status = kyc.status;

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-8">
      <div>
        <Link href={`/orders/${id}`} className="text-sm text-brand underline">← Order {id}</Link>
        <h1 className="mt-1 text-2xl font-bold">Smart KYC</h1>
        <p className="text-sm text-muted">Upload your documents. We read them, check them against the GST and Udyam registries and tell you straight away if anything needs fixing.</p>
      </div>

      {!hasConsent && (
        <Card className="space-y-4">
          <h2 className="text-lg font-semibold">Before we start: your consent</h2>
          <div className="rounded-lg bg-neutral-50 p-4 text-sm">
            <p className="font-medium">We will use your documents only to:</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">{kyc.notice.purposes.map((p) => <li key={p}>{p}</li>)}</ul>
            <p className="mt-3 font-medium">Your data, your control</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
              <li>We collect only these four documents, nothing else, and never use them for marketing.</li>
              <li>Files are encrypted at rest and automatically deleted after <b>{kyc.notice.retention_days} days</b>. Identifiers are masked on screen and in logs.</li>
              <li>You can delete everything at any time from this page and withdraw consent (DPDP Act, 2023).</li>
            </ul>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="h-5 w-5 accent-[#e40000]" checked={decl.has_gstin} onChange={(e) => setDecl({ ...decl, has_gstin: e.target.checked })} /> My business has a GSTIN</label>
            <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="h-5 w-5 accent-[#e40000]" checked={decl.has_udyam} onChange={(e) => setDecl({ ...decl, has_udyam: e.target.checked })} /> My business has a Udyam registration</label>
            {decl.has_gstin && <Field label="GSTIN (optional)" htmlFor="g" hint="We compare it with the certificate"><input id="g" className={`${inputCls} font-mono uppercase`} value={decl.gstin} onChange={(e) => setDecl({ ...decl, gstin: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 15) })} /></Field>}
            {decl.has_udyam && <Field label="Udyam number (optional)" htmlFor="u" hint="UDYAM-XX-00-0000000"><input id="u" className={`${inputCls} font-mono uppercase`} value={decl.udyam_number} onChange={(e) => setDecl({ ...decl, udyam_number: e.target.value.toUpperCase() })} /></Field>}
          </div>
          <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5 h-5 w-5 accent-[#e40000]" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> I consent to Accel Business processing my documents for the purposes above. (Notice v{kyc.notice.version})</label>
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={!consent} loading={savingConsent} onClick={giveConsent}>I agree, continue</Button>
            <span className="text-xs text-muted">Prefer not to upload? Choose &quot;field visit&quot; with your Accel contact - the digital route needs consent.</span>
          </div>
          {err && <ErrorBox>{err}</ErrorBox>}
        </Card>
      )}

      {hasConsent && (
        <>
          <Card className={cx(status === "verified" || status === "approved" ? "border-ok bg-green-50" : status === "rejected" ? "border-red-300 bg-red-50" : "")}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold">Verification status</p>
              <Badge tone={statusTone(status)}>{STATUS_TEXT[status] ?? titleCase(status)}</Badge>
            </div>
            {res ? <p className="mt-1 text-sm">{res.summary}</p> : <p className="mt-1 text-sm text-muted">Upload the documents below to begin.</p>}
            {(status === "verified" || status === "approved") && <Link href={`/orders/${id}`} className="mt-3 inline-flex min-h-11 items-center rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white">Continue to installation →</Link>}
          </Card>

          {res && res.issues.length > 0 && (
            <Card className="space-y-3">
              <p className="font-semibold">What needs your attention</p>
              <ul className="space-y-3">
                {res.issues.map((i, k) => (
                  <li key={k} className={cx("rounded-lg border-l-4 px-3 py-2 text-sm", i.severity === "reject" ? "border-red-600 bg-red-50" : i.severity === "fix" ? "border-amber-500 bg-amber-50" : "border-blue-500 bg-blue-50")}>
                    <p className="font-medium">{i.message}</p>
                    <p className="text-muted">→ {i.action}</p>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold">Documents</p>
              {samples.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <select aria-label="Sample applicant" className={`${inputCls} !w-auto !min-h-9 !py-1`} value={sample} onChange={(e) => setSample(e.target.value)}>
                    <option value="">Demo: use a specimen applicant...</option>
                    {samples.map((s) => <option key={s.id} value={s.id}>{s.id} ({s.documents.length} docs)</option>)}
                  </select>
                  <Button variant="secondary" disabled={!sample || !!busyDoc} onClick={loadSample}>Load</Button>
                </div>
              )}
            </div>
            {progress && <p className="text-sm text-muted" role="status">{progress}</p>}
            <div className="grid gap-3 md:grid-cols-2">
              {["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"].map((d) => {
                const required = kyc.required_documents.includes(d);
                const up = kyc.uploaded[d];
                const st = res?.document_status[d] ?? (up ? "ok" : required ? "missing" : "not_required");
                const info = res?.documents?.[d];
                return (
                  <div key={d} className="rounded-lg border border-line p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold">{kyc.doc_labels[d]}{!required && <span className="font-normal text-muted"> (optional)</span>}</p>
                        <p className="text-xs text-muted">{DOC_HINT[d]}</p>
                      </div>
                      <Badge tone={statusTone(st)}>{st === "ok" ? "Looks good" : st === "review" ? "Review" : st === "failed" ? "Problem" : st === "missing" ? "Missing" : st === "not_required" ? "Not needed" : titleCase(st)}</Badge>
                    </div>
                    {up && <p className="mt-1 text-xs text-muted">{up.filename} · deleted automatically on {fmtDate(up.purge_after)}</p>}
                    {info && (
                      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 rounded bg-neutral-50 p-2 text-xs">
                        {Object.entries(info.fields).filter(([, v]) => v).map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{titleCase(k)}</dt><dd className="break-words font-medium">{String(v)}</dd></div>))}
                      </dl>
                    )}
                    {info?.quality?.deskewed === true && <p className="mt-1 text-xs text-blue-700">Tilted scan straightened automatically.</p>}
                    <label className={cx("mt-3 flex min-h-11 cursor-pointer items-center justify-center rounded-lg border border-dashed px-3 text-sm font-medium", busyDoc === d ? "border-neutral-300 text-neutral-400" : "border-brand text-brand hover:bg-brand-soft")}>
                      {busyDoc === d ? "Reading document..." : up ? "Replace file" : "Choose file / take photo"}
                      <input type="file" accept="image/png,image/jpeg" className="sr-only" disabled={!!busyDoc} onChange={(e) => { onPick(d, e.target.files?.[0]); e.target.value = ""; }} />
                    </label>
                  </div>
                );
              })}
            </div>
            {err && <ErrorBox>{err}</ErrorBox>}
          </Card>

          {res && (
            <Card className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-neutral-50 p-3 text-sm"><p className="font-semibold">GST registry</p>{res.registry.gstin.found ? <p>{res.registry.gstin.trade_name} · <Badge tone={res.registry.gstin.status === "Active" ? "ok" : "bad"}>{res.registry.gstin.status}</Badge></p> : <p className="text-muted">Not matched</p>}</div>
                <div className="rounded-lg bg-neutral-50 p-3 text-sm"><p className="font-semibold">Udyam registry</p>{res.registry.udyam.found ? <p>{res.registry.udyam.enterprise_name} · {res.registry.udyam.type} enterprise</p> : <p className="text-muted">Not matched</p>}</div>
              </div>
              <button className="text-sm font-semibold text-brand underline" aria-expanded={showChecks} onClick={() => setShowChecks(!showChecks)}>{showChecks ? "Hide" : "Show"} all {res.checks.length} checks</button>
              {showChecks && (
                <ul className="divide-y divide-line text-sm">
                  {res.checks.map((c, i) => (
                    <li key={i} className="flex gap-3 py-2">
                      <span aria-label={c.status} className={cx("mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-xs font-bold text-white", c.status === "pass" ? "bg-ok" : c.status === "fail" ? "bg-red-600" : c.status === "warn" ? "bg-amber-500" : "bg-blue-500")}>{c.status === "pass" ? "✓" : c.status === "fail" ? "!" : c.status === "warn" ? "~" : "i"}</span>
                      <span><b>{c.label}</b> <span className="text-muted">- {c.detail}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          <Card className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <p className="text-muted">Consent given {kyc.consent ? fmtDate(kyc.consent.given_at) : ""}. Documents are encrypted and deleted after {kyc.consent?.retention_days} days.</p>
            <Button variant="danger" onClick={erase}>Delete my documents &amp; withdraw consent</Button>
          </Card>
        </>
      )}
    </div>
  );
}
