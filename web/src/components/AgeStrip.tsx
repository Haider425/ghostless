import type { Job } from "@/lib/api";
import { pluralize } from "@/lib/format";

import { ClockIcon } from "./Icons";

/*
  How long a posting has really been open, against how long this employer
  usually takes. It replaces the "posted 2 days ago" date that reposted
  listings show.

  The bar only appears when there is a typical time to compare against: an
  age on its own is a number, not a proportion. Its scale runs from 0 to
  whichever is larger, twice the typical time or the age itself, and the fill
  turns ochre once the posting passes the typical time.
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

function isOverdue(signals: Job["signals"]): boolean {
  const typical = signals.typical_days_open ?? null;
  return (typical !== null && signals.days_open > typical) || Boolean(signals.flags?.includes("open_unusually_long"));
}

/** The short form for job rows, where the sentence would repeat down the list. */
function shortAge(signals: Job["signals"]): string {
  const days = signals.days_open;
  if (signals.age_known === false) return days < 1 ? "Predates tracking" : `Open ${days}+ days`;
  if (days === 0) return "First seen today";
  return `Open ${pluralize(days, "day")}`;
}

/** One line for job rows: "Open 12 days · usually 30". */
export function AgeNote({ signals, isActive = true }: { signals: Job["signals"]; isActive?: boolean }) {
  const typical = signals.typical_days_open ?? null;
  const overdue = isOverdue(signals);
  return (
    <span className={`age-note inline-flex items-center gap-1 tabular-nums ${overdue ? "text-ochre" : "text-ink-soft"}`}>
      <ClockIcon className="size-3.5 shrink-0 opacity-80" />
      <span title={isActive ? ageSentence(signals) : undefined}>
        {isActive ? shortAge(signals) : `Was open ${pluralize(signals.days_open, "day")}`}
      </span>
      {typical !== null && <span className="text-ink-faint">· usually {typical}</span>}
    </span>
  );
}

export function AgeStrip({
  signals,
  company,
  isActive = true,
}: {
  signals: Job["signals"];
  company: string;
  isActive?: boolean;
}) {
  const days = signals.days_open;
  const typical = signals.typical_days_open ?? null;
  const overdue = isOverdue(signals);

  return (
    <div className="space-y-2">
      <p className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
        <span className={`font-display text-xl font-semibold tracking-tight tabular-nums ${overdue ? "text-ochre" : "text-ink"}`}>
          {isActive ? ageSentence(signals) : `Was open ${pluralize(days, "day")}`}
        </span>
        <span className="text-sm text-ink-soft">
          {typical !== null ? (
            <>
              {company} usually fills these in <span className="font-medium text-ink tabular-nums">{pluralize(typical, "day")}</span>
            </>
          ) : (
            "No typical time yet for this employer"
          )}
        </span>
      </p>
      {typical !== null && <AgeBar days={days} typical={typical} overdue={overdue} lowerBound={signals.age_known === false} />}
    </div>
  );
}

function AgeBar({ days, typical, overdue, lowerBound }: { days: number; typical: number; overdue: boolean; lowerBound: boolean }) {
  const scale = Math.max(days, typical * 2, 1);
  const fill = Math.max(1.5, Math.min(100, (days / scale) * 100));
  const typicalAt = (typical / scale) * 100;
  return (
    <div className="relative pb-4" aria-hidden="true">
      <div className="relative h-1.5 rounded-full bg-sunken">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${overdue ? "bg-ochre" : "bg-accent"} ${lowerBound ? "opacity-70" : ""}`}
          style={{ width: `${fill}%` }}
        />
        {lowerBound && (
          // the open end: this posting predates tracking, so its true start is further left
          <div className="absolute inset-y-0 left-0 w-3 rounded-l-full bg-linear-to-r from-surface/80 to-transparent" />
        )}
        <div className="absolute -top-1 h-3.5 w-px bg-ink" style={{ left: `${typicalAt}%` }} />
      </div>
      <span
        className="absolute top-3 -translate-x-1/2 text-[0.6875rem] whitespace-nowrap text-ink-faint"
        style={{ left: `${Math.min(92, Math.max(8, typicalAt))}%` }}
      >
        typical
      </span>
    </div>
  );
}
