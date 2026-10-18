import type { Job } from "@/lib/api";
import { FLAG_TEXT, LEVEL_LABELS, formatSalary, shortLocation } from "@/lib/format";

import { AgeNote } from "./AgeStrip";
import { CompanyLogo } from "./CompanyLogo";
import { JobLink } from "./JobLink";
import { MatchBadge } from "./Match";
import { RiskBadge } from "./RiskBadge";
import { SaveButton } from "./SaveButton";

type HeadingLevel = "h2" | "h3";

/**
 * One posting in a list: a row inside a JobList panel. The whole row is
 * clickable through the title link's overlay; the save button sits above it.
 * In search results, `previewHref` opens the job in the preview pane on wide
 * screens. The match score has its own slot under the save button, so it
 * appears without pushing anything around.
 */
export function JobCard({
  job,
  headingLevel = "h3",
  previewHref,
  selected = false,
}: {
  job: Job;
  headingLevel?: HeadingLevel;
  previewHref?: string;
  selected?: boolean;
}) {
  const Heading = headingLevel;
  const flags = (job.signals.flags ?? []).filter((f) => FLAG_TEXT[f]);
  return (
    <article
      className={`job-card group relative flex h-full gap-3 px-4 py-3.5 transition-colors hover:bg-sunken/60 ${
        // the selection only shows where the preview pane does
        selected ? "lg:bg-accent-tint/50 lg:before:absolute lg:before:inset-y-0 lg:before:left-0 lg:before:w-0.5 lg:before:bg-accent" : ""
      }`}
    >
      <CompanyLogo name={job.company} domain={job.company_domain} />
      <div className="min-w-0 flex-1">
        <Heading className="font-sans text-[0.9375rem] leading-snug font-semibold tracking-normal text-ink">
          <JobLink
            href={`/jobs/${job.id}`}
            previewHref={previewHref}
            current={selected}
            className="after:absolute after:inset-0 group-hover:text-accent focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-focus"
          >
            {job.title}
          </JobLink>
        </Heading>
        <p className="mt-0.5 truncate text-sm text-ink-soft">
          <span className="font-medium text-ink">{job.company}</span>
          <span aria-hidden="true" className="mx-1.5 text-ink-faint">
            ·
          </span>
          {shortLocation(job.location)}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs">
          <RiskBadge risk={job.signals.risk} />
          {flags.length > 0 && (
            <span className="font-medium text-brick">{flags.map((f) => FLAG_TEXT[f]!.short).join(" · ")}</span>
          )}
          <AgeNote signals={job.signals} isActive={job.is_active} />
          {job.salary && <span className="tag border-transparent bg-sunken text-ink">{formatSalary(job.salary)}</span>}
          <span className="tag">{LEVEL_LABELS[job.level]}</span>
          {(job.terms ?? []).slice(0, 3).map((term) => (
            <span key={term} className="tag">
              {term}
            </span>
          ))}
        </div>
      </div>
      <div className="relative z-10 -mt-1.5 -mr-2 flex w-11 shrink-0 flex-col items-center gap-1">
        <SaveButton
          job={{
            id: job.id,
            title: job.title,
            company: job.company,
            companyDomain: job.company_domain ?? null,
            location: job.location,
            url: job.url,
          }}
        />
        <MatchBadge jobId={job.id} />
      </div>
    </article>
  );
}

/**
 * Postings as rows in one panel. `columns` lays them out two across on wide
 * screens (the home page); search results and company pages use one column.
 */
export function JobList({
  jobs,
  headingLevel,
  previewHref,
  selectedId,
  columns = 1,
}: {
  jobs: Job[];
  headingLevel?: HeadingLevel;
  previewHref?: (id: number) => string;
  selectedId?: number | null;
  columns?: 1 | 2;
}) {
  return (
    <div className="panel overflow-hidden">
      <ul className={columns === 2 ? "-mb-px grid md:grid-cols-2" : "divide-y divide-line"}>
        {jobs.map((job) => (
          <li key={job.id} className={columns === 2 ? "border-b border-line md:odd:border-r" : undefined}>
            <JobCard
              job={job}
              headingLevel={headingLevel}
              previewHref={previewHref?.(job.id)}
              selected={selectedId === job.id}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
