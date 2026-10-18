import type { WeekCount } from "@/lib/api";
import { formatMonthDay } from "@/lib/format";

/*
  New vs closed postings per week: paired bars on one axis. Colours are a
  validated pair (see globals.css), with a legend, hover titles per bar, and
  the same numbers as a table for screen readers and anyone who prefers one.
*/

const W = 640;
const H = 220;
const PAD = { top: 12, right: 8, bottom: 26, left: 32 };

/** A bar rounded at its data end only, square on the baseline. */
function barPath(x: number, top: number, width: number, bottom: number): string {
  const r = Math.min(3, width / 2, bottom - top);
  return `M${x},${bottom}V${top + r}Q${x},${top} ${x + r},${top}H${x + width - r}Q${x + width},${top} ${x + width},${top + r}V${bottom}Z`;
}

function niceMax(value: number): number {
  if (value <= 4) return 4;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= value) return m * step;
  return 10 * step;
}

export function WeeklyChart({ weeks, title }: { weeks: WeekCount[]; title: string }) {
  const max = niceMax(Math.max(1, ...weeks.flatMap((w) => [w.new, w.closed])));
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(1, weeks.length);
  const bar = Math.min(14, (slot - 8) / 2);
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const ticks = [0, max / 2, max];
  const totalNew = weeks.reduce((s, w) => s + w.new, 0);
  const totalClosed = weeks.reduce((s, w) => s + w.closed, 0);

  return (
    <figure className="space-y-3">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <span className="font-sans text-base font-semibold text-ink">{title}</span>
        <span className="flex gap-4 text-sm text-ink-soft">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="size-2.5 rounded-sm bg-bar-new" />
            New <span className="font-medium text-ink">{totalNew.toLocaleString("en-CA")}</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="size-2.5 rounded-sm bg-bar-closed" />
            Closed <span className="font-medium text-ink">{totalClosed.toLocaleString("en-CA")}</span>
          </span>
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`${title}: ${totalNew} new and ${totalClosed} closed over ${weeks.length} weeks. Table below.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" />
            <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--ink-faint)">
              {Math.round(t)}
            </text>
          </g>
        ))}
        {weeks.map((w, i) => {
          const cx = PAD.left + slot * i + slot / 2;
          const label = `Week of ${formatMonthDay(w.week_start)}`;
          return (
            <g key={w.week_start} className="[&:hover_.mark]:opacity-75">
              <rect x={cx - slot / 2} y={PAD.top} width={slot} height={plotH} fill="transparent">
                <title>{`${label}: ${w.new} new, ${w.closed} closed`}</title>
              </rect>
              {w.new > 0 && (
                <path className="mark pointer-events-none" d={barPath(cx - bar - 1, Math.min(y(w.new), y(0) - 1), bar, y(0))} fill="var(--bar-new)" />
              )}
              {w.closed > 0 && (
                <path className="mark pointer-events-none" d={barPath(cx + 1, Math.min(y(w.closed), y(0) - 1), bar, y(0))} fill="var(--bar-closed)" />
              )}
              {i % 2 === (weeks.length - 1) % 2 && (
                <text x={cx} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--ink-faint)">
                  {formatMonthDay(w.week_start)}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" strokeWidth="1" />
      </svg>
      <details className="text-sm">
        <summary className="inline-block text-ink-soft hover:text-ink">Show the numbers</summary>
        <table className="mt-2 w-full max-w-sm text-left">
          <thead>
            <tr className="text-ink-soft">
              <th scope="col" className="py-1 font-medium">Week of</th>
              <th scope="col" className="py-1 text-right font-medium">New</th>
              <th scope="col" className="py-1 text-right font-medium">Closed</th>
            </tr>
          </thead>
          <tbody>
            {weeks.map((w) => (
              <tr key={w.week_start} className="border-t border-line">
                <th scope="row" className="py-1 font-normal text-ink">{formatMonthDay(w.week_start)}</th>
                <td className="py-1 text-right">{w.new}</td>
                <td className="py-1 text-right">{w.closed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
