import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import type { ReactNode } from "react";

import { CompanyLogo } from "@/components/CompanyLogo";
import { SearchIcon } from "@/components/Icons";
import { Pagination } from "@/components/Pagination";
import { type Company, api } from "@/lib/api";
import { type SearchParams } from "@/lib/filters";
import { percent, pluralize } from "@/lib/format";

export const metadata: Metadata = {
  title: "Companies",
  description: "Every employer Ghostless tracks: open tech roles, new postings this week, time to fill and ghost risk.",
};

const SORTS = {
  open: { label: "Most open roles", by: (a: Company, b: Company) => b.tech_active_jobs - a.tech_active_jobs },
  new: { label: "Most new this week", by: (a: Company, b: Company) => b.new_last_7_days - a.new_last_7_days },
  fastest: {
    label: "Fastest to fill",
    by: (a: Company, b: Company) => (a.typical_days_open ?? 9999) - (b.typical_days_open ?? 9999),
  },
  risk: {
    label: "Most ghost risk",
    by: (a: Company, b: Company) => b.high_risk_jobs / Math.max(1, b.active_jobs) - a.high_risk_jobs / Math.max(1, a.active_jobs),
  },
} as const;
type SortKey = keyof typeof SORTS;
const PER_PAGE = 60;
const SOURCES = { all: "All", boards: "Career sites", lists: "From job lists" } as const;
type Source = keyof typeof SOURCES;

function href(params: { sort: SortKey; q: string; source: Source; page?: number }): string {
  const query = new URLSearchParams();
  if (params.sort !== "open") query.set("sort", params.sort);
  if (params.q) query.set("q", params.q);
  if (params.source !== "all") query.set("source", params.source);
  if (params.page && params.page > 1) query.set("page", String(params.page));
  const text = query.toString();
  return text ? `/companies?${text}` : "/companies";
}

export default async function CompaniesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await connection();
  const params = await searchParams;
  const raw = params.sort;
  const sort: SortKey = typeof raw === "string" && raw in SORTS ? (raw as SortKey) : "open";
  const q = typeof params.q === "string" ? params.q.trim().slice(0, 80) : "";
  const source: Source = typeof params.source === "string" && params.source in SOURCES ? (params.source as Source) : "all";
  const everyone = await api.companies();
  const fromLists = everyone.filter((c) => c.origin === "list").length;
  const totalOpen = everyone.reduce((sum, c) => sum + c.tech_active_jobs, 0);
  const needle = q.toLowerCase();
  const companies = everyone
    .filter((c) => (source === "all" ? true : source === "lists" ? c.origin === "list" : c.origin !== "list"))
    .filter((c) => !needle || c.name.toLowerCase().includes(needle))
    .sort((a, b) => SORTS[sort].by(a, b) || a.name.localeCompare(b.name));
  const pages = Math.max(1, Math.ceil(companies.length / PER_PAGE));
  const page = Math.min(pages, Math.max(1, Math.trunc(Number(params.page)) || 1));
  const shown = companies.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <header className="mb-6 max-w-3xl">
        <h1 className="text-3xl font-semibold text-ink">Companies</h1>
        <p className="mt-2 text-ink-soft">
          {pluralize(everyone.length, "employer")} and {totalOpen.toLocaleString("en-CA")} open tech roles.{" "}
          {(everyone.length - fromLists).toLocaleString("en-CA")} are read every day from their own career sites; the rest
          come from public internship and new grad lists until Ghostless finds their job board.
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <form action="/companies" method="get" role="search" className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          {sort !== "open" && <input type="hidden" name="sort" value={sort} />}
          <label className="relative min-w-0 flex-1 sm:max-w-xs">
            <span className="sr-only">Search companies</span>
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint" />
            <input type="search" name="q" defaultValue={q} placeholder="Search companies" className="field pl-9" />
          </label>
          <select name="source" defaultValue={source} aria-label="Where the jobs come from" className="field w-auto text-sm">
            {(Object.keys(SOURCES) as Source[]).map((key) => (
              <option key={key} value={key}>{SOURCES[key]}</option>
            ))}
          </select>
          <button type="submit" className="btn btn-secondary">Search</button>
        </form>
        <nav aria-label="Sort companies" className="max-w-full overflow-x-auto">
          <ul className="flex rounded-lg border border-line bg-sunken/60 p-0.5 text-sm">
            {(Object.keys(SORTS) as SortKey[]).map((key) => (
              <li key={key}>
                <Link
                  href={href({ sort: key, q, source })}
                  aria-current={sort === key ? "true" : undefined}
                  className="inline-flex h-7 items-center rounded-md px-2.5 font-medium whitespace-nowrap text-ink-soft transition-colors hover:text-ink aria-[current=true]:bg-surface aria-[current=true]:text-ink aria-[current=true]:shadow-[0_0_0_1px_var(--line-strong)]"
                >
                  {SORTS[key].label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      {!shown.length ? (
        <p className="panel border-dashed p-6 text-sm text-ink-soft">
          No companies match. <Link href="/companies" className="link">Show all</Link>.
        </p>
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Companies, sorted by {SORTS[sort].label.toLowerCase()}. {pluralize(companies.length, "company", "companies")}.
            </caption>
            <thead>
              <tr className="border-b border-line bg-sunken/50 text-left text-xs text-ink-soft">
                <th scope="col" className="w-full px-3 py-2.5 sm:px-4 font-medium">Company</th>
                <Th active={sort === "open"}>
                  <span className="sm:hidden">Open</span>
                  <span className="hidden sm:inline">Open tech roles</span>
                </Th>
                <Th active={sort === "new"} className="hidden sm:table-cell">
                  New this week <span className="font-normal text-ink-faint">(all roles)</span>
                </Th>
                <Th active={sort === "fastest"} order="ascending" className="hidden md:table-cell">Usually fills in</Th>
                <Th active={sort === "risk"}>
                  <span className="sm:hidden">High risk</span>
                  <span className="hidden sm:inline">High ghost risk</span>
                </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shown.map((company) => {
                const share = company.active_jobs ? company.high_risk_jobs / company.active_jobs : 0;
                return (
                  <tr key={company.slug} className="group transition-colors hover:bg-sunken/50">
                    <th scope="row" className="w-full max-w-0 px-3 py-2.5 sm:px-4 text-left font-normal">
                      <div className="flex items-center gap-3">
                        <CompanyLogo name={company.name} domain={company.domain} size="sm" />
                        <div className="min-w-0">
                          <Link href={`/companies/${company.slug}`} className="block truncate font-medium text-ink group-hover:text-accent">
                            {company.name}
                          </Link>
                          {company.origin === "list" && <span className="block truncate text-xs text-ink-faint">From job lists</span>}
                        </div>
                      </div>
                    </th>
                    <td className="px-3 py-2.5 sm:px-4 text-right font-medium whitespace-nowrap text-ink">{company.tech_active_jobs.toLocaleString("en-CA")}</td>
                    <td className="hidden px-3 py-2.5 sm:px-4 text-right text-ink sm:table-cell">
                      {company.new_last_7_days ? company.new_last_7_days.toLocaleString("en-CA") : <span className="text-ink-faint">0</span>}
                    </td>
                    <td className="hidden px-3 py-2.5 sm:px-4 text-right md:table-cell">
                      {company.typical_days_open ? (
                        <span className="text-ink">{pluralize(company.typical_days_open, "day")}</span>
                      ) : (
                        <span className="text-ink-faint">Not enough data</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 sm:px-4 text-right whitespace-nowrap">
                      {company.high_risk_jobs ? (
                        <span className={share >= 0.2 ? "font-semibold text-brick" : "text-ink"}>
                          {percent(company.high_risk_jobs, company.active_jobs)}
                          <span className="ml-1.5 text-xs font-normal text-ink-faint">{company.high_risk_jobs.toLocaleString("en-CA")}</span>
                        </span>
                      ) : (
                        <span className="text-ink-faint">None</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-ink-faint">
        High ghost risk is the share of each employer&apos;s open postings, all roles, with high-risk signals; the small number is the
        count.
      </p>
      <Pagination page={page} total={companies.length} pageSize={PER_PAGE} href={(p) => href({ sort, q, source, page: p })} />
    </div>
  );
}

/** A numeric column heading; the column the list is sorted by is marked. */
function Th({
  children,
  active,
  order = "descending",
  className = "",
}: {
  children: ReactNode;
  active: boolean;
  order?: "ascending" | "descending";
  className?: string;
}) {
  return (
    <th scope="col" aria-sort={active ? order : undefined} className={`px-3 py-2.5 sm:px-4 text-right font-medium whitespace-nowrap ${active ? "text-ink" : ""} ${className}`}>
      {children}
    </th>
  );
}
