export interface User { id: string; email: string; name: string; phone?: string | null; role: "customer" | "admin" }

export interface Profile {
  business_name: string; business_type: string; city: string; employees: number; sites: number; current_internet: string;
  monthly_budget?: number | null; monthly_telecom_spend?: number | null; has_gstin: boolean; has_udyam: boolean;
  contact_name?: string | null; phone?: string | null; segment: string; city_tier: number; state: string; gstin_status: string; gstin_masked?: string | null;
}
export interface Journey { id: string; stage: string; language: string; profile: Profile; needs: Record<string, unknown>; selection: Selection | null; propensity?: number }
export interface Selection { items: { product_id: string; quantity: number }[]; term_months: number; tier?: string }

export interface Meta {
  cities: { city: string; tier: number; state: string }[];
  business_types: { business_type: string; segment: string }[];
  internet_options: string[]; segments: string[];
  languages: { code: string; label: string }[];
}

export interface Eligibility { status: "yes" | "conditional" | "no"; reasons: { code: string; message: string }[]; unlock: string[] }
export interface CatalogueItem {
  product_id: string; category: string; name: string; description: string; unit: string; price_min: number; price_max: number; setup_fee: number;
  min_contract_months: number; requires_gstin: boolean; requires_one_of: string[]; install_days: number; min_employees: number; min_sites: number;
  city_tiers: number[]; eligibility: Eligibility; default_quantity: number; segment_attach_rate: number;
}
export interface QuoteLine {
  product_id: string; name: string; category: string; unit: string; quantity: number; unit_price: number; list_unit_price: number; floor_unit_price: number;
  discounts: { label: string; position: number }[]; monthly: number; setup_unit: number; setup: number; install_days: number; min_contract_months: number;
}
export interface Totals {
  monthly_subtotal: number; monthly_gst: number; monthly_total: number; setup_subtotal: number; setup_gst: number; setup_total: number; first_payment: number;
  term_months: number; contract_value: number; list_monthly_subtotal: number; discount_vs_list: number; gst_rate_percent: number; gst_note: string;
  install_days: number; term_options: number[]; required_term_months: number; current_monthly_spend?: number; vs_current_spend?: number;
}
export interface Quote { items: QuoteLine[]; totals: Totals }
export interface BundleItem { product_id: string; name: string; unit: string; category: string; quantity: number; role: string; reasons: string[] }
export interface Tier { name: string; items: BundleItem[]; term_months: number; quote: Quote | null }
export interface Recommendation {
  tiers: Record<"starter" | "recommended" | "complete", Tier>; recommended_tier: "starter" | "recommended" | "complete"; over_budget: boolean; budget: number | null;
  excluded: { product_id: string; name: string; eligibility: Eligibility }[]; notes: string[]; segment: string;
}
export interface PreviewResult {
  valid: boolean; errors: { code: string; message: string; product_id?: string }[]; quote: Quote | null; indicative_quote?: Quote;
  fixes: { product_id: string; add_one_of: { product_id: string; name: string }[]; or_remove: string }[];
}
export interface SavedQuote { id: string; journey_id: string; term_months: number; items: QuoteLine[]; totals: Totals }

export interface AdvisorReply {
  reply: string; question?: string | null; chips: string[]; recommendation_ready: boolean; provider: string;
  understood?: string[]; progress?: { asked: number; max: number };
  summary?: { tier: string; monthly_total: number; setup_total: number; items: number };
}

export interface TrackerStep { key: string; label: string; state: "done" | "current" | "pending" | "failed" | "blocked" | "review" | "cancelled" }
export interface Order {
  id: string; status: string; kyc_status: string; payment_status: string; business_name: string; term_months: number; monthly_total: number; setup_total: number;
  install_slot: { date: string; window: string; window_label: string } | null; expected_activation: string | null; activated_on: string | null; typical_install_days: number;
  created_at: string; events: { status: string; note: string; actor: string; at: string }[];
  tracker: { steps: TrackerStep[]; next_action: { type: string; message: string } | null };
  items?: QuoteLine[]; totals?: Totals; customer?: string;
}

export interface KycCheck { id: string; label: string; status: "pass" | "fail" | "warn" | "info"; detail: string; doc: string | null }
export interface KycIssue { code: string; severity: "reject" | "fix" | "review"; doc: string | null; message: string; action: string }
export interface KycReport {
  status: string; summary: string; required_documents: string[]; document_status: Record<string, string>; checks: KycCheck[]; issues: KycIssue[];
  next_actions: string[];
  registry: { gstin: { found: boolean; status?: string; trade_name?: string; gstin?: string }; udyam: { found: boolean; enterprise_name?: string; type?: string; udyam_number?: string } };
  documents?: Record<string, { label: string; filename: string; fields: Record<string, string | null>; quality: Record<string, unknown>; status: string }>;
}
export interface KycCase {
  case_id: string; status: string; consent: { given_at: string; retention_days: number } | null; required_documents: string[];
  uploaded: Record<string, { filename: string; uploaded_at: string; purge_after: string | null }>;
  declared: Record<string, string | boolean>; result: KycReport | null;
  notice: { version: string; purposes: string[]; retention_days: number }; doc_labels: Record<string, string>;
}

export type PaymentMethod = "upi" | "card" | "netbanking";
export type PaymentStatus = "created" | "pending" | "succeeded" | "failed" | "expired" | "cancelled";
export type NextAction =
  | { type: "upi_collect"; message: string }
  | { type: "upi_intent"; message: string; intent_url: string }
  | { type: "redirect"; message: string; url: string; bank: string }
  | { type: "card_otp"; message: string }
  | { type: "hosted_checkout"; message: string; key_id: string; gateway_order_id: string; amount: number; currency: string; name: string; description: string; prefill: Record<string, string> };
export interface Payment {
  id: string; order_id: string; method: PaymentMethod; method_label: string; description: string; amount: number; amount_paise: number; currency: string;
  status: PaymentStatus; next_action: NextAction | null; failure_code: string | null; failure_message: string | null; details: Record<string, unknown>;
  attempt_no: number; receipt: string; gateway: string; expires_at: string; paid_at: string | null; created_at: string; order_payment_status?: string;
}
export interface PaymentMethods {
  gateway: string; hosted_checkout: boolean; expiry_minutes: number;
  methods: { id: PaymentMethod; label: string }[]; banks: { code: string; name: string }[];
  sandbox_hints?: Record<PaymentMethod, string[]>;
}
