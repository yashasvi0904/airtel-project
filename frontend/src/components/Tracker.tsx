"use client";
import type { TrackerStep } from "@/lib/types";
import { cx } from "./ui";

const ICON: Record<string, string> = { done: "✓", current: "●", pending: "", failed: "!", blocked: "!", review: "…", cancelled: "×" };
const RING: Record<string, string> = {
  done: "bg-ok text-white border-ok", current: "bg-white text-brand border-brand", pending: "bg-white text-neutral-300 border-neutral-300",
  failed: "bg-red-600 text-white border-red-600", blocked: "bg-red-600 text-white border-red-600", review: "bg-amber-500 text-white border-amber-500", cancelled: "bg-neutral-400 text-white border-neutral-400",
};

export default function Tracker({ steps }: { steps: TrackerStep[] }) {
  return (
    <ol className="grid gap-0 sm:grid-cols-6" aria-label="Order progress">
      {steps.map((s, i) => (
        <li key={s.key} className="relative flex gap-3 pb-6 sm:flex-col sm:items-center sm:gap-2 sm:pb-0 sm:text-center" aria-current={s.state === "current" ? "step" : undefined}>
          {i < steps.length - 1 && (
            <>
              <span aria-hidden className={cx("absolute left-4 top-8 h-full w-0.5 sm:hidden", s.state === "done" ? "bg-ok" : "bg-neutral-200")} />
              <span aria-hidden className={cx("absolute left-1/2 top-4 hidden h-0.5 w-full sm:block", s.state === "done" ? "bg-ok" : "bg-neutral-200")} />
            </>
          )}
          <span className={cx("relative z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 text-sm font-bold", RING[s.state])}>{ICON[s.state]}</span>
          <span className="pt-1 sm:pt-0">
            <span className={cx("block text-sm font-medium", s.state === "pending" && "text-muted")}>{s.label}</span>
            {s.state === "review" && <span className="block text-xs text-amber-700">Under review</span>}
            {(s.state === "failed" || s.state === "blocked") && <span className="block text-xs text-red-700">Needs attention</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
