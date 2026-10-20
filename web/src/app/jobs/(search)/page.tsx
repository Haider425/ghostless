import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { FilterBar } from "@/components/FilterBar";
import { CloseIcon } from "@/components/Icons";
import { JobList } from "@/components/JobCard";
import { MatchPanel, MatchScores } from "@/components/Match";
import { MatchesLink } from "@/components/MatchesLink";
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

function resultsLabel(total: number, role: RoleScope): string {
  const what = role === "tech" ? "tech " : role === "all" ? "" : `${ROLE_LABELS_INLINE[role]} `;
  return `${total.toLocaleString("en-CA")} ${what}${total === 1 ? "job" : "jobs"}`;
}

/**
 * The next eight seasons (the API lists only seasons that haven't started),
 * plus any season already chosen, so a shared link's filter can still be unticked.
 */
function seasonOptions(upcoming: { term: string; jobs: number }[], chosen: string[]) {
  const shown = upcoming.slice(0, 8);
  const missing = chosen.filter((term) => !shown.some((s) => s.term === term));
  return [...missing.map((term) => upcoming.find((s) => s.term === term) ?? { term, jobs: 0 }), ...shown];
}

/** The selected job, in the right-hand pane on wide screens. */
function Preview({ job }: { job: JobDetail }) {
  return (
    <div
      data-preview
      key={job.id /* new job, new scroll position */}
      className="panel scroll-quiet sticky top-[calc(var(--header-h)+1.5rem)] max-h-[calc(100dvh-var(--header-h)-3rem)] overflow-y-auto"
    >
      <div className="space-y-6 p-8">
        <JobHeader job={job} titleAs="h2" showPageLink />
        {/* the record first: it's what Ghostless adds; the personal match follows */}
        <PostingRecord job={job} headingAs="h3" />
        <MatchPanel jobId={job.id} hasDescription={Boolean(job.description)} headingAs="h3" />
        <PostingHistory job={job} headingAs="h3" />
        <Disclosures job={job} headingAs="h3" />
        <SkillChips skills={job.skills} headingAs="h3" />
        <JobDescription job={job} headingAs="h3" />
        <p className="text-ui text-ink-soft">
          Something wrong with this posting? <ReportDialog jobId={job.id} label="Report it" className="link" />
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
    <div className="px-4 pt-6 pb-16 sm:px-6 lg:px-10 lg:pt-7">
      <h1 className="sr-only">Search jobs</h1>
      <FilterBar filters={filters} seasons={seasonOptions(seasons, filters.term)} />
      <div className="mt-5">
        <RoleTabs filters={filters} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,32rem)_minmax(0,1fr)]">
        <section aria-labelledby="results-heading" className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 lg:px-4">
            <h2 id="results-heading" aria-live="polite" className="text-ui font-semibold text-ink tabular-nums">
              {resultsLabel(page.total, filters.role)}
              {filters.q && (
                <span className="font-normal text-ink-soft">
                  {" "}
                  matching &ldquo;{filters.q}&rdquo;
                </span>
              )}
            </h2>
            <MatchesLink />
          </div>

          {removable.length > 0 && (
            <ul className="mt-2 mb-2 flex flex-wrap gap-2 px-1 lg:px-4">
              {removable.map(({ label, href }) => (
                <li key={label}>
                  <Link href={href} className="tag gap-1.5 bg-accent-tint pr-2 pl-3 text-accent hover:underline">
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
              <div className="-mx-4 sm:mx-0">
                <MatchScores jobIds={page.items.map((j) => j.id)}>
                  <JobList
                    jobs={page.items}
                    headingLevel="h3"
                    bare
                    previewHref={(id) => jobsHref(filters, { selected: id })}
                    selectedId={selected?.id ?? null}
                  />
                </MatchScores>
              </div>
              <Pagination page={filters.page} total={page.total} pageSize={PAGE_SIZE} href={(p) => jobsHref(filters, { page: p })} />
            </>
          ) : (
            <EmptyState title="No postings match these filters">
              <p>
                Try removing a filter or searching for a broader title.{" "}
                <Link href="/jobs" className="link">
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
