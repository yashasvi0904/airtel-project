"use client";
import { useLang } from "@/lib/i18n";

export default function Footer() {
  const { tr } = useLang();
  return (
    <footer className="border-t border-line bg-white py-6 text-center text-xs text-muted">
      <p className="mx-auto max-w-3xl px-4">{tr("Accel Business · Udyam Digital prototype. All businesses and data shown are synthetic. Payments run on a test gateway - no real money moves.")}</p>
    </footer>
  );
}
