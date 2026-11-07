"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";

/**
 * One "Back" control for the whole app. It goes to the logical previous step of the journey (not raw browser history),
 * so Back from KYC can never bounce the customer into the payment page and forward again.
 *   onboarding <- advisor <- bundle <- checkout ... order <- pay | kyc
 */
function parentOf(path: string): string | null {
  if (path === "/") return null;
  if (path === "/pay/bank") return null; // mid-payment bank page: leaving must go through the bank's own buttons
  const order = path.match(/^\/orders\/([^/]+)(?:\/(pay|kyc))?$/);
  if (order) return order[2] ? `/orders/${order[1]}` : "/orders";
  return ({ "/onboarding": "/", "/advisor": "/onboarding", "/bundle": "/advisor", "/checkout": "/bundle", "/orders": "/", "/login": "/", "/register": "/", "/admin": "/" } as Record<string, string>)[path] ?? "/";
}

export default function BackBar() {
  const path = usePathname();
  const { tr } = useLang();
  const parent = parentOf(path);
  if (!parent) return null;
  return (
    <nav aria-label="Back" className="mx-auto w-full max-w-5xl px-4 pt-3">
      <Link href={parent} className="inline-flex min-h-11 items-center gap-1 rounded-lg pr-3 text-sm font-medium text-brand hover:underline">
        <span aria-hidden="true" className="text-lg leading-none">←</span> {tr("Back")}
      </Link>
    </nav>
  );
}
