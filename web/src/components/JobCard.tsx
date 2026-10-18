import type { Job } from "@/lib/api";
import { FLAG_TEXT, LEVEL_LABELS, formatSalary, shortLocation } from "@/lib/format";

import { AgeStrip } from "./AgeStrip";
import { CompanyLogo } from "./CompanyLogo";
import { PinIcon } from "./Icons";
import { JobLink } from "./JobLink";
import { MatchBadge } from "./Match";
import { RiskBadge } from "./RiskBadge";
import { SaveButton } from "./SaveButton";

type HeadingLevel = "h2" | "h3";

/**
 * One posting in a list. The whole card is clickable through the title link's
 * overlay; the save button sits above it. In search results, `previewHref`
 * opens the job in the preview pane on wide screens.
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
      className={`job-card group relative flex gap-3 rounded-xl border p-4 transition-colors ${
        // the selection only shows where the preview pane does
        selected
          ? "border-line bg-surface hover:border-line-strong lg:border-accent lg:ring-1 lg:ring-accent"
          : "border-line bg-surface hover:border-line-strong"
      }`}
    >
      <CompanyLogo name={job.company} domain={job.company_domain} />
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <Heading className="pr-8 font-sans text-base leading-snug font-semibold text-ink">
            <JobLink
              href={`/jobs/${job.id}`}
              previewHref={previewHref}
              current={selected}
              className="after:absolute after:inset-0 after:rounded-xl group-hover:text-accent focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-focus"
            >
              {job.title}
            </JobLink>
          </Heading>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-ink-soft">
            <span className="font-medium text-ink">{job.company}</span>
            <span className="inline-flex items-center gap-1">
              <PinIcon className="size-3.5 text-ink-faint" />
              {shortLocation(job.location)}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <MatchBadge jobId={job.id} />
          <RiskBadge risk={job.signals.risk} />
          {job.salary && (
            <span className="rounded-full bg-accent-tint px-2.5 py-0.5 font-medium text-accent">
              {formatSalary(job.salary)}
            </span>
          )}
          <span className="rounded-full bg-sunken px-2.5 py-0.5 text-ink-soft">{LEVEL_LABELS[job.level]}</span>
          {(job.terms ?? []).slice(0, 3).map((term) => (
            <span key={term} className="rounded-full border border-line-strong px-2.5 py-0.5 text-ink-soft">
              {term}
            </span>
          ))}
          {flags.map((flag) => (
            <span key={flag} className="rounded-full border border-brick/30 px-2.5 py-0.5 text-brick">
              {FLAG_TEXT[flag]!.short}
            </span>
          ))}
        </div>
        <AgeStrip signals={job.signals} company={job.company} isActive={job.is_active} compact />
      </div>
      <div className="absolute top-3 right-3">
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
      </div>
    </article>
  );
}

export function JobList({
  jobs,
  headingLevel,
  previewHref,
  selectedId,
}: {
  jobs: Job[];
  headingLevel?: HeadingLevel;
  previewHref?: (id: number) => string;
  selectedId?: number | null;
}) {
  return (
    <ul className="space-y-3">
      {jobs.map((job) => (
        <li key={job.id}>
          <JobCard
            job={job}
            headingLevel={headingLevel}
            previewHref={previewHref?.(job.id)}
            selected={selectedId === job.id}
          />
        </li>
      ))}
    </ul>
  );
}
