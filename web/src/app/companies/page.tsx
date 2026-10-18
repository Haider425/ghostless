import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { CompanyLogo } from "@/components/CompanyLogo";
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
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl space-y-2">
          <h1 className="text-4xl font-semibold text-ink">Companies</h1>
          <p className="text-lg text-ink-soft">
            {pluralize(everyone.length, "employer")} and {totalOpen.toLocaleString("en-CA")} open tech roles.{" "}
            {(everyone.length - fromLists).toLocaleString("en-CA")} are read every day from their own career sites; the rest
            come from public internship and new grad lists until Ghostless finds their job board.
          </p>
        </div>
        <nav aria-label="Sort companies">
          <ul className="flex flex-wrap gap-2 text-sm">
            {(Object.keys(SORTS) as SortKey[]).map((key) => (
              <li key={key}>
                <Link
                  href={href({ sort: key, q, source })}
                  aria-current={sort === key ? "true" : undefined}
                  className="inline-block rounded-full border border-line-strong bg-surface px-3.5 py-1.5 font-medium text-ink hover:border-ink-faint aria-[current=true]:border-accent aria-[current=true]:bg-accent-tint aria-[current=true]:text-accent"
                >
                  {SORTS[key].label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      <form action="/companies" method="get" role="search" className="mb-6 flex flex-wrap items-center gap-3">
        {sort !== "open" && <input type="hidden" name="sort" value={sort} />}
        <label className="min-w-0 flex-1 sm:max-w-sm">
          <span className="sr-only">Search companies</span>
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search companies"
            className="h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
          />
        </label>
        <select name="source" defaultValue={source} aria-label="Where the jobs come from" className="h-10 rounded-lg border border-line-strong bg-surface px-2 text-sm text-ink">
          {(Object.keys(SOURCES) as Source[]).map((key) => (
            <option key={key} value={key}>{SOURCES[key]}</option>
          ))}
        </select>
        <button type="submit" className="h-10 rounded-lg bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-hover">Search</button>
        <p className="text-sm text-ink-soft" aria-live="polite">{pluralize(companies.length, "company", "companies")}</p>
      </form>

      {!shown.length && <p className="text-ink-soft">No companies match. <Link href="/companies" className="text-accent hover:underline">Show all</Link>.</p>}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((company) => {
          const share = company.active_jobs ? company.high_risk_jobs / company.active_jobs : 0;
          return (
            <li key={company.slug}>
              <article className="group relative h-full rounded-xl border border-line bg-surface p-5 transition-colors hover:border-line-strong">
                <div className="flex items-center gap-3">
                  <CompanyLogo name={company.name} domain={company.domain} />
                  <h2 className="font-sans text-lg font-semibold text-ink">
                    <Link
                      href={`/companies/${company.slug}`}
                      className="after:absolute after:inset-0 after:rounded-xl group-hover:text-accent"
                    >
                      {company.name}
                    </Link>
                  </h2>
                </div>
                {company.origin === "list" && <p className="mt-1 text-xs text-ink-faint">From job lists</p>}
                <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <dt className="text-ink-soft">Open roles</dt>
                    <dd className="font-display text-xl font-semibold text-ink">{company.tech_active_jobs.toLocaleString("en-CA")}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-soft">New this week</dt>
                    <dd className="font-display text-xl font-semibold text-ink">{company.new_last_7_days.toLocaleString("en-CA")}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-soft">Fills in</dt>
                    <dd className="font-display text-xl font-semibold text-ink">
                      {company.typical_days_open ? `${company.typical_days_open}d` : <span className="text-base font-normal text-ink-faint">No data</span>}
                    </dd>
                  </div>
                </dl>
                <p className="mt-4 border-t border-line pt-3 text-sm text-ink-soft">
                  {company.high_risk_jobs ? (
                    <>
                      <span className={share >= 0.2 ? "font-semibold text-brick" : "font-medium text-ink"}>
                        {percent(company.high_risk_jobs, company.active_jobs)}
                      </span>{" "}
                      of open postings are high ghost risk
                    </>
                  ) : (
                    "No high-risk postings right now"
                  )}
                </p>
              </article>
            </li>
          );
        })}
      </ul>
      <Pagination page={page} total={companies.length} pageSize={PER_PAGE} href={(p) => href({ sort, q, source, page: p })} />
    </div>
  );
}
