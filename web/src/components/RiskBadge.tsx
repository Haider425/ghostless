import type { GhostRisk } from "@/lib/api";
import { RISK_LABELS } from "@/lib/format";

/* Pastel status chips: mint for no flags, butter for some, blush for high. Lists only show flagged postings. */
const STYLES: Record<GhostRisk, string> = {
  low: "chip-good",
  medium: "chip-warn",
  high: "chip-bad",
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
    <span className={`chip ${size === "md" ? "chip-md" : ""} ${STYLES[risk]}`}>
      <Glyph risk={risk} />
      {RISK_LABELS[risk]}
    </span>
  );
}
