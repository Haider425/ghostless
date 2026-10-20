import type { ReactNode } from "react";

/**
 * A labelled figure, one cell of a StatStrip. `tone` marks figures that are a
 * warning sign.
 */
export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: "warn" }) {
  return (
    <div className="card px-5 py-4.5">
      <dt className="label">{label}</dt>
      <dd
        className={`mt-1 text-3xl font-bold tracking-[-0.025em] ${tone === "warn" ? "text-brick" : "text-ink"}`}
      >
        {value}
      </dd>
      {note && <dd className="mt-0.5 text-meta text-ink-faint">{note}</dd>}
    </div>
  );
}

/** Figures side by side in one panel, divided by hairlines rather than boxed one by one. */
export function StatStrip({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <dl className={`grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4 ${className}`}>
      {children}
    </dl>
  );
}
