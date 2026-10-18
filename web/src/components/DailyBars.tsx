import { formatMonthDay } from "@/lib/format";

/*
  One series per day as bars on a single axis. Each bar has a hover title,
  and the numbers are available as a table, so nothing depends on the chart.
*/

const W = 640;
const H = 160;
const PAD = { top: 10, right: 6, bottom: 22, left: 30 };

function niceMax(value: number): number {
  if (value <= 4) return 4;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= value) return m * step;
  return 10 * step;
}

export function DailyBars({ title, days, values, unit }: { title: string; days: string[]; values: number[]; unit: string }) {
  const max = niceMax(Math.max(1, ...values));
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(1, values.length);
  const bar = Math.max(2, slot - 2); // 2px gap between bars
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const total = values.reduce((a, b) => a + b, 0);
  const every = Math.ceil(values.length / 6);

  return (
    <figure className="space-y-2">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="font-sans text-sm font-semibold text-ink">{title}</span>
        <span className="text-sm text-ink-soft">
          <span className="font-semibold text-ink">{total.toLocaleString("en-CA")}</span> in {values.length} days
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`${title}: ${total} ${unit} over ${values.length} days. Table below.`}>
        {[0, max / 2, max].map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize="10" fill="var(--ink-faint)">
              {Math.round(t)}
            </text>
          </g>
        ))}
        {values.map((v, i) => {
          const x = PAD.left + slot * i + 1;
          const top = Math.min(y(v), y(0) - (v > 0 ? 1 : 0));
          return (
            <g key={days[i]} className="[&:hover_.mark]:opacity-70">
              <rect x={x - 1} y={PAD.top} width={slot} height={plotH} fill="transparent">
                <title>{`${formatMonthDay(days[i] ?? "")}: ${v} ${unit}`}</title>
              </rect>
              {v > 0 && (
                <path
                  className="mark pointer-events-none"
                  d={`M${x},${y(0)}V${top + 2}Q${x},${top} ${x + 2},${top}H${x + bar - 2}Q${x + bar},${top} ${x + bar},${top + 2}V${y(0)}Z`}
                  fill="var(--accent)"
                />
              )}
              {i % every === (values.length - 1) % every && (
                <text x={x + bar / 2} y={H - 6} textAnchor="middle" fontSize="10" fill="var(--ink-faint)">
                  {formatMonthDay(days[i] ?? "")}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" />
      </svg>
      <details className="text-sm">
        <summary className="inline-block text-ink-soft hover:text-ink">Show the numbers</summary>
        <table className="mt-2 w-full max-w-xs text-left">
          <tbody>
            {values.map((v, i) => (
              <tr key={days[i]} className="border-t border-line">
                <th scope="row" className="py-0.5 font-normal text-ink">{formatMonthDay(days[i] ?? "")}</th>
                <td className="py-0.5 text-right">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
