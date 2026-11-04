"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, journeyStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import type { Journey, Meta } from "@/lib/types";
import { Button, Card, ErrorBox, Field, Loading, inputCls } from "@/components/ui";

interface GstLookup { found: boolean; checksum_valid: boolean; format_valid: boolean; status?: string; trade_name?: string; state?: string }

const INITIAL = {
  business_name: "", business_type: "", city: "", employees: "3", sites: "1", current_internet: "Mobile hotspot", monthly_budget: "", monthly_telecom_spend: "",
  has_gstin: false, gstin: "", has_udyam: false, contact_name: "", phone: "",
};

export default function Onboarding() {
  const router = useRouter();
  const { user } = useAuth();
  const { lang, t } = useLang();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaErr, setMetaErr] = useState("");
  const [f, setF] = useState(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitErr, setSubmitErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [gst, setGst] = useState<GstLookup | null>(null);

  const load = () => api<Meta>("/meta").then(setMeta).catch((e: ApiError) => setMetaErr(e.message));
  useEffect(() => { load(); }, []);
  useEffect(() => { if (user && !f.contact_name) setF((p) => ({ ...p, contact_name: user.name, phone: user.phone ?? p.phone })); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k: keyof typeof INITIAL, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  const cityInfo = useMemo(() => meta?.cities.find((c) => c.city === f.city), [meta, f.city]);

  // Instant GSTIN check against the mock registry (needs sign-in only for rate limiting; fall back silently)
  useEffect(() => {
    const g = f.gstin.trim().toUpperCase();
    setGst(null);
    if (g.length !== 15) return;
    const h = setTimeout(() => { api<GstLookup>(`/registry/gstin/${g}`).then(setGst).catch(() => setGst(null)); }, 300);
    return () => clearTimeout(h);
  }, [f.gstin]);

  function validate() {
    const e: Record<string, string> = {};
    if (!f.business_name.trim()) e.business_name = "Enter your business name";
    if (!f.business_type) e.business_type = "Choose a category";
    if (!f.city) e.city = "Choose your city";
    const emp = Number(f.employees);
    if (!Number.isInteger(emp) || emp < 1 || emp > 5000) e.employees = "Enter a number between 1 and 5000";
    const sites = Number(f.sites);
    if (!Number.isInteger(sites) || sites < 1 || sites > 500) e.sites = "Enter a number between 1 and 500";
    if (f.monthly_budget && (isNaN(Number(f.monthly_budget)) || Number(f.monthly_budget) < 0)) e.monthly_budget = "Enter an amount in rupees";
    if (f.phone && !/^[6-9]\d{9}$/.test(f.phone.replace(/\D/g, "").slice(-10))) e.phone = "Enter a 10-digit mobile number";
    if (f.gstin && f.gstin.trim().length !== 15) e.gstin = "A GSTIN has 15 characters";
    if (gst && f.gstin.length === 15 && !gst.found) e.gstin = gst.checksum_valid ? "This GSTIN is not in the GST registry" : "This GSTIN fails its checksum - check for a typo";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setSubmitErr("");
    if (!validate()) return;
    setBusy(true);
    try {
      const j = await api<Journey>("/journeys", {
        body: {
          business_name: f.business_name.trim(), business_type: f.business_type, city: f.city, employees: Number(f.employees), sites: Number(f.sites),
          current_internet: f.current_internet, monthly_budget: f.monthly_budget ? Number(f.monthly_budget) : null,
          monthly_telecom_spend: f.monthly_telecom_spend ? Number(f.monthly_telecom_spend) : null,
          has_gstin: f.has_gstin || !!f.gstin, gstin: f.gstin.trim().toUpperCase() || null, has_udyam: f.has_udyam,
          contact_name: f.contact_name.trim() || null, phone: f.phone.trim() || null, language: lang,
        },
      });
      journeyStore.set(j.id);
      router.push("/advisor");
    } catch (e) {
      setSubmitErr(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (metaErr) return <div className="mx-auto max-w-2xl p-4"><ErrorBox onRetry={() => { setMetaErr(""); load(); }}>{metaErr}</ErrorBox></div>;
  if (!meta) return <Loading />;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold">{t("ob_title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("ob_sub")}</p>
      <form onSubmit={submit} noValidate className="mt-6 space-y-5">
        <Card className="grid gap-4 sm:grid-cols-2">
          <Field label="Business name" error={errors.business_name} htmlFor="bn">
            <input id="bn" className={inputCls} value={f.business_name} onChange={(e) => set("business_name", e.target.value)} placeholder="e.g. Sharma Kirana Store" maxLength={160} />
          </Field>
          <Field label="Business category" error={errors.business_type} htmlFor="bt">
            <select id="bt" className={inputCls} value={f.business_type} onChange={(e) => set("business_type", e.target.value)}>
              <option value="">Select...</option>
              {meta.business_types.map((b) => <option key={b.business_type} value={b.business_type}>{b.business_type}</option>)}
            </select>
          </Field>
          <Field label="City" error={errors.city} hint={cityInfo ? `${cityInfo.state} · tier ${cityInfo.tier} city` : "We currently serve tier 1 and tier 2 cities"} htmlFor="city">
            <select id="city" className={inputCls} value={f.city} onChange={(e) => set("city", e.target.value)}>
              <option value="">Select...</option>
              {meta.cities.map((c) => <option key={c.city} value={c.city}>{c.city}</option>)}
            </select>
          </Field>
          <Field label="Current connectivity" htmlFor="ci">
            <select id="ci" className={inputCls} value={f.current_internet} onChange={(e) => set("current_internet", e.target.value)}>
              {meta.internet_options.map((o) => <option key={o}>{o}</option>)}
            </select>
          </Field>
          <Field label="Number of employees" error={errors.employees} htmlFor="emp">
            <input id="emp" inputMode="numeric" className={inputCls} value={f.employees} onChange={(e) => set("employees", e.target.value.replace(/\D/g, ""))} />
          </Field>
          <Field label="Number of branches / sites" error={errors.sites} hint="Include your main location" htmlFor="sites">
            <input id="sites" inputMode="numeric" className={inputCls} value={f.sites} onChange={(e) => set("sites", e.target.value.replace(/\D/g, ""))} />
          </Field>
          <Field label="Monthly budget for telecom & digital (₹)" error={errors.monthly_budget} hint="Optional - we will stay within it where possible" htmlFor="mb">
            <input id="mb" inputMode="numeric" className={inputCls} value={f.monthly_budget} onChange={(e) => set("monthly_budget", e.target.value.replace(/\D/g, ""))} placeholder="e.g. 5000" />
          </Field>
          <Field label="What you spend today (₹/month)" hint="Optional - lets us show your saving" htmlFor="ms">
            <input id="ms" inputMode="numeric" className={inputCls} value={f.monthly_telecom_spend} onChange={(e) => set("monthly_telecom_spend", e.target.value.replace(/\D/g, ""))} placeholder="e.g. 2500" />
          </Field>
        </Card>

        <Card className="space-y-4">
          <div>
            <p className="font-semibold">Registrations</p>
            <p className="text-xs text-muted">A valid, active GSTIN unlocks products like leased lines, SD-WAN, WhatsApp API and bulk SMS. You can add it later.</p>
          </div>
          <Field label="GSTIN (optional)" error={errors.gstin} htmlFor="gstin" hint="15 characters, e.g. 27XXXXX0000X1ZX">
            <input id="gstin" className={`${inputCls} font-mono uppercase`} value={f.gstin} onChange={(e) => set("gstin", e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 15))} placeholder="Enter GSTIN to verify instantly" />
          </Field>
          {gst && gst.found && (
            <p className={`rounded-lg px-3 py-2 text-sm ${gst.status === "Active" ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"}`}>
              Found: <b>{gst.trade_name}</b> ({gst.state}) - registration is <b>{gst.status}</b>
              {gst.status !== "Active" && ". GSTIN-only products will not be offered while it is not active."}
            </p>
          )}
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input type="checkbox" className="h-5 w-5 accent-[#e40000]" checked={f.has_udyam} onChange={(e) => set("has_udyam", e.target.checked)} />
            I have a Udyam registration
          </label>
        </Card>

        <Card className="grid gap-4 sm:grid-cols-2">
          <Field label="Your name" htmlFor="cn"><input id="cn" className={inputCls} value={f.contact_name} onChange={(e) => set("contact_name", e.target.value)} maxLength={120} /></Field>
          <Field label="Mobile number" error={errors.phone} htmlFor="ph"><input id="ph" inputMode="tel" className={inputCls} value={f.phone} onChange={(e) => set("phone", e.target.value)} placeholder="10-digit number" /></Field>
        </Card>

        {submitErr && <ErrorBox>{submitErr}</ErrorBox>}
        <Button type="submit" loading={busy} className="w-full sm:w-auto sm:px-8">{t("submit_ob")} →</Button>
      </form>
    </div>
  );
}
