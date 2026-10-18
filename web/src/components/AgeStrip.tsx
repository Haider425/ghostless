import type { Job } from "@/lib/api";
import { pluralize } from "@/lib/format";

/*
  The age strip: how long a posting has really been open, against how long
  this employer usually takes. It replaces the "posted 2 days ago" date that
  reposted listings show.

  Scale runs from 0 to whichever is larger: twice the typical time, the age
  itself, or 30 days. The fill turns ochre once the posting passes the
  typical time, so an overdue listing stands out at a glance.
*/

export function ageSentence(signals: Job["signals"]): string {
  const days = signals.days_open;
  if (signals.age_known === false) {
    // up before tracking began, so the true age is longer than what we've seen
    return days < 1 ? "Already up when tracking began today" : `Open at least ${pluralize(days, "day")}`;
  }
  if (days === 0) return "First seen today";
  return `Open ${pluralize(days, "day")}`;
}

export function AgeStrip({
  signals,
  company,
  isActive = true,
  compact = false,
}: {
  signals: Job["signals"];
  company: string;
  isActive?: boolean;
  compact?: boolean;
}) {
  const days = signals.days_open;
  const typical = signals.typical_days_open ?? null;
  const scale = Math.max(30, days, typical ? typical * 2 : 0);
  const fill = Math.max(2, Math.min(100, (days / scale) * 100));
  const typicalAt = typical ? (typical / scale) * 100 : null;
  const overdue = typical !== null && days > typical;

  return (
    <div className={compact ? "space-y-1" : "space-y-1.5"}>
      <div className="relative h-1.5 overflow-visible rounded-full bg-sunken" aria-hidden="true">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${overdue ? "bg-ochre" : "bg-accent"} ${
            signals.age_known === false ? "opacity-70" : ""
          }`}
          style={{ width: `${fill}%` }}
        />
        {signals.age_known === false && (
          // the open end: this posting predates tracking, so its true start is further left
          <div className="absolute inset-y-0 left-0 w-3 rounded-l-full bg-gradient-to-r from-surface/80 to-transparent" />
        )}
        {typicalAt !== null && (
          <div
            className="absolute -top-1 h-3.5 w-0.5 rounded-full bg-ink"
            style={{ left: `calc(${typicalAt}% - 1px)` }}
          />
        )}
      </div>
      <p className={`text-ink-soft ${compact ? "age-note text-xs" : "text-sm"}`}>
        <span className="font-medium text-ink">{isActive ? ageSentence(signals) : `Was open ${pluralize(days, "day")}`}.</span>{" "}
        {compact ? (
          typical !== null && <>Usually {pluralize(typical, "day")}.</>
        ) : typical !== null ? (
          <>
            {company} usually fills these in {pluralize(typical, "day")}.
          </>
        ) : (
          <>Not enough history yet to know how long {company} usually takes.</>
        )}
      </p>
    </div>
  );
}
