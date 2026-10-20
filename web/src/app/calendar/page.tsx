import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { CompanyLogo } from "@/components/CompanyLogo";
import { EmptyState } from "@/components/EmptyState";
import { type CalendarEntry, api } from "@/lib/api";
import { LEVEL_LABELS, ROLE_LABELS_INLINE, formatMonthDay } from "@/lib/format";

export const metadata: Metadata = {
  title: "Hiring calendar",
  description: "When each employer opened its internship and new grad roles, so you can be ready next season.",
};

type Props = { searchParams: Promise<{ level?: string | string[] }> };
type CalendarLevel = "intern" | "new_grad";

const LEVEL_TABS: { value: CalendarLevel; label: string }[] = [
  { value: "intern", label: "Internships and co-ops" },
  { value: "new_grad", label: "New grad" },
];

const DAY = 86_400_000;
/** The page renders per request (connection() above), so reading the clock here is safe. */
const currentTime = () => Date.now();
const at = (iso: string) => new Date(`${iso}T12:00:00`).getTime();

/**
 * A hiring season runs July to June: internships for the next summer open
 * from late summer through spring. Dates sit on that 12-month line.
 */
function season(entries: CalendarEntry[]) {
  const first = new Date(Math.min(...entries.map((e) => at(e.first_opened))));
  const startYear = first.getMonth() >= 6 ? first.getFullYear() : first.getFullYear() - 1;
  const start = new Date(startYear, 6, 1, 12).getTime();
  const end = new Date(startYear + 1, 6, 1, 12).getTime();
  const months = Array.from({ length: 12 }, (_, i) =>
    new Intl.DateTimeFormat("en-CA", { month: "short" }).format(new Date(startYear, 6 + i, 1)),
  );
  const pos = (ms: number) => Math.min(100, Math.max(0, ((ms - start) / (end - start)) * 100));
  return { start, end, months, pos, label: `${startYear}–${String(startYear + 1).slice(2)} season` };
}

function byCompany(entries: CalendarEntry[]) {
  const groups = new Map<string, CalendarEntry[]>();
  for (const entry of entries) groups.set(entry.company, [...(groups.get(entry.company) ?? []), entry]);
  return [...groups.entries()]
    .map(([company, rows]) => ({
      company,
      rows: rows.sort((a, b) => a.first_opened.localeCompare(b.first_opened)),
      first: rows.reduce((m, r) => (r.first_opened < m ? r.first_opened : m), rows[0]!.first_opened),
      postings: rows.reduce((n, r) => n + r.postings, 0),
    }))
    .sort((a, b) => a.first.localeCompare(b.first) || a.company.localeCompare(b.company));
}

export default async function CalendarPage({ searchParams }: Props) {
  await connection();
  const raw = (await searchParams).level;
  const level: CalendarLevel = (Array.isArray(raw) ? raw[0] : raw) === "new_grad" ? "new_grad" : "intern";
  const entries = await api.calendar({ level: [level] });
  const seasons = new Map<string, CalendarEntry[]>();
  for (const entry of entries) {
    const s = season([entry]).label;
    seasons.set(s, [...(seasons.get(s) ?? []), entry]);
  }
  const today = currentTime();

  return (
    <div className="mx-auto max-w-7xl px-4 pt-10 pb-20 sm:px-6 lg:px-20">
      <div className="mb-8 max-w-2xl">
        <h1 className="page-title">Hiring calendar</h1>
        <p className="page-lead">
          When each employer first opened internship and new grad roles. Most open around the same time every year, so this
          year&apos;s dates are your best guide to next season.
        </p>
      </div>

      <nav aria-label="Level" className="mb-6 flex flex-wrap gap-2">
        {LEVEL_TABS.map(({ value, label }) => (
          <Link
            key={value}
            href={value === "intern" ? "/calendar" : `/calendar?level=${value}`}
            aria-current={level === value ? "page" : undefined}
            className="inline-flex h-10 items-center rounded-full border border-line-strong px-4 text-ui font-medium text-ink hover:bg-sunken aria-[current=page]:border-ink aria-[current=page]:bg-ink aria-[current=page]:text-paper"
          >
            {label}
          </Link>
        ))}
      </nav>

      {seasons.size === 0 ? (
        <EmptyState title="The calendar fills in as roles open">
          <p>
            Ghostless records the day each student role first appears. Dates show up here as employers open new postings.{" "}
            <Link href="/jobs?level=intern&level=new_grad" className="link">
              Browse current student roles
            </Link>
            .
          </p>
        </EmptyState>
      ) : (
        [...seasons.entries()]
          .sort(([a], [b]) => b.localeCompare(a))
          .map(([label, list]) => {
            const s = season(list);
            const now = today >= s.start && today < s.end ? s.pos(today) : null;
            const companies = byCompany(list);
            return (
              <section key={label} aria-labelledby={`season-${label}`} className="mb-10">
                <h2 id={`season-${label}`} className="mb-3 text-lg font-semibold text-ink">
                  {label} <span className="font-normal text-ink-faint">· {companies.length.toLocaleString("en-CA")} employers</span>
                </h2>
                <div className="panel scroll-quiet overflow-x-auto">
                  <div className="min-w-232 lg:min-w-208">
                    <div className="grid grid-cols-[11rem_minmax(0,1fr)_6.5rem_4.5rem] sm:grid-cols-[15rem_minmax(0,1fr)_7rem_5rem] items-center gap-4 border-b border-line bg-sunken px-6 py-3 text-meta font-semibold text-ink-soft">
                      <span>Company</span>
                      <span className="grid grid-cols-12" aria-hidden="true">
                        {s.months.map((m, i) => (
                          <span key={`${m}-${i}`} className="pl-1">
                            {m}
                          </span>
                        ))}
                      </span>
                      <span>First opened</span>
                      <span className="text-right">Postings</span>
                    </div>
                    <ul className="divide-y divide-line">
                      {companies.map(({ company, rows, first, postings }) => (
                        <li key={company} className="grid grid-cols-[11rem_minmax(0,1fr)_6.5rem_4.5rem] sm:grid-cols-[15rem_minmax(0,1fr)_7rem_5rem] items-center gap-4 px-6 py-3">
                          <Link
                            href={`/jobs?company=${encodeURIComponent(company)}&level=${level}`}
                            className="flex min-w-0 items-center gap-3 text-ui font-semibold text-ink hover:text-accent"
                          >
                            <CompanyLogo name={company} size="sm" />
                            <span className="truncate">{company}</span>
                          </Link>
                          <div className="relative h-5" aria-hidden="true">
                            <div className="absolute inset-0 grid grid-cols-12">
                              {s.months.map((m, i) => (
                                <span key={`${m}-${i}`} className="border-l border-line" />
                              ))}
                            </div>
                            <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-line" />
                            {now !== null && <div className="absolute -inset-y-1 w-0.5 rounded-full bg-ink-faint" style={{ left: `${now}%` }} />}
                            {rows.map((row) => {
                              const from = s.pos(at(row.first_opened));
                              const to = s.pos(at(row.last_opened) + DAY / 2);
                              return (
                                <span
                                  key={`${row.level}-${row.role_type}`}
                                  title={`${LEVEL_LABELS[row.level]}, ${ROLE_LABELS_INLINE[row.role_type]}: ${formatMonthDay(row.first_opened)}${
                                    row.last_opened !== row.first_opened ? ` to ${formatMonthDay(row.last_opened)}` : ""
                                  }, ${row.postings} ${row.postings === 1 ? "posting" : "postings"}`}
                                  className="absolute top-1/2 h-3 min-w-3 -translate-y-1/2 rounded-full bg-accent-solid"
                                  style={{ left: `calc(${from}% - 6px)`, width: `calc(${Math.max(0, to - from)}% + 12px)` }}
                                />
                              );
                            })}
                          </div>
                          <span className="text-ui font-medium text-ink tabular-nums">{formatMonthDay(first)}</span>
                          <span className="text-right text-ui text-ink-soft tabular-nums">
                            {postings}
                            <span className="sr-only">
                              {" "}
                              postings:{" "}
                              {rows
                                .map(
                                  (r) =>
                                    `${LEVEL_LABELS[r.level]}, ${ROLE_LABELS_INLINE[r.role_type]}, ${formatMonthDay(r.first_opened)}${
                                      r.last_opened !== r.first_opened ? ` to ${formatMonthDay(r.last_opened)}` : ""
                                    }`,
                                )
                                .join("; ")}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>
            );
          })
      )}
      <p className="text-sm text-ink-faint">
        Each dot is a group of {level === "intern" ? "internship and co-op" : "new grad"} roles, placed on the day Ghostless first saw
        one; a bar runs to the last one that opened. The line marks today. Dates fill in as employers open roles.
      </p>
    </div>
  );
}
