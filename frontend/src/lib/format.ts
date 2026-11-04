const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const rupees = (n: number | null | undefined, decimals = false) =>
  n == null ? "-" : `₹${(decimals && !Number.isInteger(n) ? inr2 : inr0).format(n)}`;

export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "-";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};

export const fmtDateTime = (iso: string) => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

export const titleCase = (s: string) =>
  s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bKyc\b/g, "KYC")
    .replace(/\bGstin\b/g, "GSTIN")
    .replace(/\bGst\b/g, "GST")
    .replace(/\bId\b/g, "ID");
