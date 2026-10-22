import type { Job } from "@/lib/api";
import { pluralize } from "@/lib/format";


/*
  How long a posting has really been open, against how long this employer
  usually takes. It replaces the "posted 2 days ago" date that reposted
  listings show.

  The bar compares the age with the employer's typical time, or with two
  months while there's no typical time yet. Its scale runs from 0 to
  whichever is larger, twice that mark or the age itself, and the fill turns
  ochre once the posting is overdue.
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

/** Postings Ghostless saw appear in the last few days. */
const FRESH_DAYS = 3;

/**
 * A row's age as a status chip: mint while fresh (seen appearing in the last
 * few days), butter once it's past the employer's usual time, the warm
 * neutral otherwise. The employer's usual time is on the job's own page.
 */
export function AgeNote({ signals, isActive = true }: { signals: Job["signals"]; isActive?: boolean }) {
  const overdue = isOverdue(signals);
  const fresh = isActive && signals.age_known !== false && signals.days_open <= FRESH_DAYS;
  const tone = !isActive ? "chip-neutral" : overdue ? "chip-warn" : fresh ? "chip-good" : "chip-neutral";
  return (
    <span className={`age-note chip tabular-nums ${tone}`} title={isActive ? ageSentence(signals) : undefined}>
      {isActive ? shortAge(signals) : `Was open ${pluralize(signals.days_open, "day")}`}
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
    <div className="space-y-3">
      <p className="flex flex-col gap-1">
        <span className={`text-3xl leading-tight font-bold tracking-[-0.02em] tabular-nums ${overdue ? "text-ochre" : "text-ink"}`}>
          {isActive ? ageSentence(signals) : `Was open ${pluralize(days, "day")}`}
        </span>
        <span className="text-ui text-ink-soft">
          {typical !== null ? (
            <>
              {company} usually fills these in <span className="font-medium text-ink tabular-nums">{pluralize(typical, "day")}</span>
            </>
          ) : (
            "No typical time yet for this employer"
          )}
        </span>
      </p>
      <AgeBar days={days} typical={typical} overdue={overdue} lowerBound={signals.age_known === false} />
    </div>
  );
}

/** Without the employer's usual time yet, the bar is read against two months. */
const REFERENCE_DAYS = 60;

function AgeBar({ days, typical, overdue, lowerBound }: { days: number; typical: number | null; overdue: boolean; lowerBound: boolean }) {
  const mark = typical ?? REFERENCE_DAYS;
  const scale = Math.max(days, mark * 2, 1);
  const fill = Math.max(1.5, Math.min(100, (days / scale) * 100));
  const typicalAt = (mark / scale) * 100;
  return (
    <div className="relative pb-5" aria-hidden="true">
      <div className="relative h-2 rounded-full bg-hover">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${overdue ? "bg-ochre" : "bg-accent-solid"} ${lowerBound ? "opacity-70" : ""}`}
          style={{ width: `${fill}%` }}
        />
        {lowerBound && (
          // the open end: this posting predates tracking, so its true start is further left
          <div className="absolute inset-y-0 left-0 w-3 rounded-l-full bg-linear-to-r from-surface/80 to-transparent" />
        )}
        <div className="absolute -top-1 h-4 w-0.5 rounded-full bg-ink" style={{ left: `${typicalAt}%` }} />
      </div>
      <span
        className="absolute top-4 -translate-x-1/2 text-xs font-medium whitespace-nowrap text-ink-faint"
        style={{ left: `${Math.min(92, Math.max(8, typicalAt))}%` }}
      >
        {typical !== null ? "typical" : "2 months"}
      </span>
    </div>
  );
}
