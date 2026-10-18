import type { ReactNode } from "react";

/** A labelled figure. `tone` marks figures that are a warning sign. */
export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: "warn" }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <dt className="text-sm text-ink-soft">{label}</dt>
      <dd className={`mt-1 font-display text-3xl font-semibold tracking-tight ${tone === "warn" ? "text-brick" : "text-ink"}`}>
        {value}
      </dd>
      {note && <dd className="mt-1 text-xs text-ink-faint">{note}</dd>}
    </div>
  );
}
