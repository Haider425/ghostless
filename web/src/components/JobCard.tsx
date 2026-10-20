import type { Job } from "@/lib/api";
import { LEVEL_LABELS, formatSalary, shortLocation } from "@/lib/format";

import { AgeNote } from "./AgeStrip";
import { CompanyLogo } from "./CompanyLogo";
import { JobLink } from "./JobLink";
import { MatchBadge } from "./Match";
import { RiskBadge } from "./RiskBadge";
import { SaveButton } from "./SaveButton";

type HeadingLevel = "h2" | "h3";

/**
 * One posting in a list. Title, company, then "place · level · pay" as plain
 * text. Below: how long it has really been open, and a risk tag only when a
 * posting has flags ("No flags" is the normal case, so it stays quiet). The
 * save button and, with a resume, the match ring sit on the right.
 *
 * The whole row is clickable through the title link's overlay; the save
 * button sits above it. In search results, `previewHref` opens the job in the
 * preview pane on wide screens.
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
  const risk = job.signals.risk;
  const facts = [shortLocation(job.location), LEVEL_LABELS[job.level], job.salary ? formatSalary(job.salary) : null].filter(Boolean);
  return (
    <article
      className={`job-card group relative flex gap-3.5 rounded-xl p-4 transition-colors hover:bg-sunken ${
        // the selection only shows where the preview pane does
        selected ? "lg:bg-sunken" : ""
      }`}
    >
      <CompanyLogo name={job.company} domain={job.company_domain} />
      <div className="min-w-0 flex-1">
        <Heading className="text-base leading-snug font-semibold text-ink">
          <JobLink
            href={`/jobs/${job.id}`}
            previewHref={previewHref}
            current={selected}
            className="after:absolute after:inset-0 after:rounded-xl group-hover:text-accent focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-0 focus-visible:after:outline-focus"
          >
            {job.title}
          </JobLink>
        </Heading>
        <p className="mt-0.5 truncate text-sm text-ink-soft">{job.company}</p>
        <p className="truncate text-sm text-ink-faint">{facts.join(" · ")}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
          <AgeNote signals={job.signals} isActive={job.is_active} />
          {(risk === "medium" || risk === "high") && <RiskBadge risk={risk} />}
        </div>
      </div>
      <div className="relative z-10 -mt-1.5 -mr-1.5 flex shrink-0 flex-col items-end gap-1.5">
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
        <div className="pr-1.5">
          <MatchBadge jobId={job.id} />
        </div>
      </div>
    </article>
  );
}

/**
 * Postings as rounded rows. `bare` drops the surrounding card (the search
 * page's list sits straight on the page); elsewhere the rows sit in a card.
 * `columns` lays them out two across on wide screens.
 */
export function JobList({
  jobs,
  headingLevel,
  previewHref,
  selectedId,
  columns = 1,
  bare = false,
}: {
  jobs: Job[];
  headingLevel?: HeadingLevel;
  previewHref?: (id: number) => string;
  selectedId?: number | null;
  columns?: 1 | 2;
  bare?: boolean;
}) {
  return (
    <div className={bare ? "" : "panel p-2"}>
      <ul className={`grid grid-cols-[minmax(0,1fr)] gap-0.5 ${columns === 2 ? "md:grid-cols-2" : ""}`}>
        {jobs.map((job) => (
          <li key={job.id}>
            <JobCard job={job} headingLevel={headingLevel} previewHref={previewHref?.(job.id)} selected={selectedId === job.id} />
          </li>
        ))}
      </ul>
    </div>
  );
}
