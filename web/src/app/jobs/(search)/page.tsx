import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { FILTER_FORM_ID, FilterBar } from "@/components/FilterBar";
import { CloseIcon } from "@/components/Icons";
import { JobList } from "@/components/JobCard";
import { MatchPanel, MatchScores } from "@/components/Match";
import { ReportDialog } from "@/components/ReportDialog";
import { RoleTabs } from "@/components/RoleTabs";
import {
  Disclosures,
  JobDescription,
  JobHeader,
  PostingHistory,
  PostingRecord,
  SkillChips,
} from "@/components/JobDetailParts";
import { Pagination } from "@/components/Pagination";
import { type JobDetail, api } from "@/lib/api";
import { PAGE_SIZE, type SearchParams, activeFilterCount, jobsHref, parseFilters, toApiQuery } from "@/lib/filters";
import { LEVEL_LABELS, ROLE_LABELS_INLINE } from "@/lib/format";
import type { RoleScope } from "@/lib/filters";

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const filters = parseFilters(await searchParams);
  const parts = [filters.q, ...filters.level.map((l) => LEVEL_LABELS[l])].filter(Boolean);
  return {
    title: parts.length ? `${parts.join(", ")} jobs` : "Search tech jobs",
    description: "Tech jobs with their true posting age, repost history and ghost job signals.",
    alternates: { canonical: "/jobs" },
    // filtered result pages are endless permutations: let search engines index only the base page
    robots: activeFilterCount(filters) || filters.q || filters.page > 1 || filters.selected ? { index: false } : undefined,
  };
}

const SORT_LABELS = { newest: "Newest first", oldest: "Oldest first", salary: "Highest pay", company: "Company A to Z" };

function resultsLabel(total: number, role: RoleScope): string {
  const what = role === "tech" ? "tech " : role === "all" ? "" : `${ROLE_LABELS_INLINE[role]} `;
  return `${total.toLocaleString("en-CA")} ${what}${total === 1 ? "job" : "jobs"}`;
}

/** The selected job, in the right-hand pane on wide screens. */
function Preview({ job }: { job: JobDetail }) {
  return (
    <div
      data-preview
      key={job.id /* new job, new scroll position */}
      className="scroll-quiet sticky top-20 max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-2xl border border-line bg-surface"
    >
      <div className="border-b border-line p-6">
        <JobHeader job={job} titleAs="h2" showPageLink />
      </div>
      <div className="space-y-5 p-6">
        <MatchPanel jobId={job.id} hasDescription={Boolean(job.description)} headingAs="h3" />
        <PostingRecord job={job} headingAs="h3" />
        <PostingHistory job={job} headingAs="h3" />
        <Disclosures job={job} headingAs="h3" />
        <SkillChips skills={job.skills} headingAs="h3" />
        <JobDescription job={job} headingAs="h3" />
        <p className="border-t border-line pt-4 text-sm text-ink-soft">
          Something wrong with this posting? <ReportDialog jobId={job.id} label="Report it" className="font-medium text-accent hover:underline" />
        </p>
      </div>
    </div>
  );
}

export default async function JobsPage({ searchParams }: Props) {
  const filters = parseFilters(await searchParams);
  const [page, seasons] = await Promise.all([api.jobs(toApiQuery(filters)), api.terms().catch(() => [])]);
  const selectedId = filters.selected ?? page.items[0]?.id ?? null;
  const selected = selectedId ? await api.job(selectedId) : null;
  const removable = [
    ...filters.company.map((c) => ({ label: c, href: jobsHref(filters, { company: filters.company.filter((x) => x !== c), page: 1 }) })),
    ...filters.skill.map((s) => ({ label: s, href: jobsHref(filters, { skill: filters.skill.filter((x) => x !== s), page: 1 }) })),
  ];

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <h1 className="sr-only">Search jobs</h1>
      <div className="mb-4">
        <FilterBar filters={filters} seasons={seasons.slice(0, 8)} />
      </div>
      <div className="mb-5">
        <RoleTabs filters={filters} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,25rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
        <section aria-labelledby="results-heading" className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <h2 id="results-heading" aria-live="polite" className="font-sans text-sm font-semibold text-ink">
              {resultsLabel(page.total, filters.role)}
              {filters.q && (
                <span className="font-normal text-ink-soft">
                  {" "}
                  matching &ldquo;{filters.q}&rdquo;
                </span>
              )}
            </h2>
            <label className="flex items-center gap-2 text-sm text-ink-soft">
              Sort
              <select
                key={filters.sort}
                name="sort"
                form={FILTER_FORM_ID}
                defaultValue={filters.sort}
                className="h-9 rounded-lg border border-line-strong bg-surface px-2 text-sm text-ink"
              >
                {Object.entries(SORT_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {removable.length > 0 && (
            <ul className="mb-3 flex flex-wrap gap-2 text-sm">
              {removable.map(({ label, href }) => (
                <li key={label}>
                  <Link
                    href={href}
                    className="inline-flex items-center gap-1.5 rounded-full bg-accent-tint py-1 pr-2 pl-3 font-medium text-accent hover:bg-accent hover:text-on-accent"
                  >
                    {label}
                    <CloseIcon className="size-3.5" />
                    <span className="sr-only">remove {label} filter</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {page.items.length ? (
            <>
              <MatchScores jobIds={page.items.map((j) => j.id)}>
                <JobList
                  jobs={page.items}
                  headingLevel="h3"
                  previewHref={(id) => jobsHref(filters, { selected: id })}
                  selectedId={selected?.id ?? null}
                />
              </MatchScores>
              <Pagination page={filters.page} total={page.total} pageSize={PAGE_SIZE} href={(p) => jobsHref(filters, { page: p })} />
            </>
          ) : (
            <EmptyState title="No postings match these filters">
              <p>
                Try removing a filter or searching for a broader title.{" "}
                <Link href="/jobs" className="font-medium text-accent hover:underline">
                  Clear everything
                </Link>
                .
              </p>
            </EmptyState>
          )}
        </section>

        <div className="hidden min-w-0 lg:block">{selected && <Preview job={selected} />}</div>
      </div>
    </div>
  );
}
