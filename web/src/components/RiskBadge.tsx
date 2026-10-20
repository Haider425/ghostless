import type { GhostRisk } from "@/lib/api";
import { RISK_LABELS } from "@/lib/format";

/* "No flags" is the common case, so it stays quiet; only flagged postings get a filled badge. */
const STYLES: Record<GhostRisk, string> = {
  low: "text-ink-soft",
  medium: "bg-ochre-tint text-ochre",
  high: "bg-brick-tint text-brick",
};

/** Shape differs per level too, so risk never depends on colour alone. */
function Glyph({ risk }: { risk: GhostRisk }) {
  if (risk === "high") {
    return (
      <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true">
        <path d="M6 1 11 10.5H1Z" fill="currentColor" />
      </svg>
    );
  }
  if (risk === "medium") {
    return (
      <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true">
        <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M6 1.5a4.5 4.5 0 0 1 0 9Z" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true">
      <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function RiskBadge({ risk, size = "sm" }: { risk: GhostRisk | null | undefined; size?: "sm" | "md" }) {
  if (!risk) {
    return <span className="text-meta text-ink-faint">Signals pending</span>;
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full font-medium ${STYLES[risk]} ${
        size === "md" ? "h-7 text-sm" : "h-6 text-meta"
      } ${risk === "low" ? "" : size === "md" ? "pr-3 pl-2.5" : "pr-2.5 pl-2"}`}
    >
      <Glyph risk={risk} />
      {RISK_LABELS[risk]}
    </span>
  );
}
