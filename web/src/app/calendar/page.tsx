import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { EmptyState } from "@/components/EmptyState";
import { type CalendarEntry, api } from "@/lib/api";
import { LEVEL_LABELS, ROLE_LABELS_INLINE, formatMonthDay } from "@/lib/format";

export const metadata: Metadata = {
  title: "Hiring calendar",
  description: "When each employer opened its internship and new grad roles, so you can be ready next season.",
};

export default async function CalendarPage() {
  await connection();
  const entries = await api.calendar({});
  const years = [...new Set(entries.map((e) => e.year))].sort((a, b) => b - a);
  const byCompany = (year: number) => {
    const groups = new Map<string, CalendarEntry[]>();
    for (const entry of entries.filter((e) => e.year === year)) {
      groups.set(entry.company, [...(groups.get(entry.company) ?? []), entry]);
    }
    return [...groups.entries()].sort(
      ([, a], [, b]) => (a[0]?.first_opened ?? "").localeCompare(b[0]?.first_opened ?? ""),
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="mb-8 max-w-2xl space-y-2">
        <h1 className="text-4xl font-semibold text-ink">Hiring calendar</h1>
        <p className="text-ink-soft">
          When each employer first opened internship and new grad roles. Most employers open around the same time
          every year, so this year&apos;s dates are your best guide to next season.
        </p>
      </div>

      {years.length === 0 ? (
        <EmptyState title="The calendar fills in as roles open">
          <p>
            Ghostless records the day each student role first appears. Dates show up here as employers open new
            postings.{" "}
            <Link href="/jobs?level=intern&level=new_grad" className="text-accent hover:underline">
              Browse current student roles
            </Link>
            .
          </p>
        </EmptyState>
      ) : (
        years.map((year) => (
          <section key={year} aria-labelledby={`year-${year}`} className="mb-10">
            <h2 id={`year-${year}`} className="mb-3 text-xl font-semibold text-ink">
              {year}
            </h2>
            <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
              <table className="w-full min-w-[36rem] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line bg-paper text-left text-ink-soft">
                    <th scope="col" className="px-4 py-3 font-medium">Company</th>
                    <th scope="col" className="px-4 py-3 font-medium">Roles</th>
                    <th scope="col" className="px-4 py-3 font-medium">First opened</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Postings</th>
                  </tr>
                </thead>
                {byCompany(year).map(([company, rows]) => (
                  // one row group per company, so its rowspan header is scoped correctly
                  <tbody key={company} className="border-b border-line last:border-0">
                    {rows.map((row, i) => (
                      <tr key={`${row.level}-${row.role_type}`}>
                        {i === 0 && (
                          <th
                            scope="rowgroup"
                            rowSpan={rows.length}
                            className="px-4 py-3 text-left align-top font-medium text-ink"
                          >
                            <Link
                              href={`/jobs?company=${encodeURIComponent(company)}&level=intern&level=new_grad`}
                              className="hover:underline"
                            >
                              {company}
                            </Link>
                          </th>
                        )}
                        <td className="px-4 py-3 text-ink-soft">
                          {LEVEL_LABELS[row.level]}, {ROLE_LABELS_INLINE[row.role_type]}
                        </td>
                        <td className="px-4 py-3 font-medium text-ink">
                          {formatMonthDay(row.first_opened)}
                          {row.last_opened !== row.first_opened && (
                            <span className="font-normal text-ink-faint"> to {formatMonthDay(row.last_opened)}</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-ink">{row.postings}</td>
                      </tr>
                    ))}
                  </tbody>
                ))}
              </table>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
