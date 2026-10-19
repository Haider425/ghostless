import Link from "next/link";
import type { ReactNode } from "react";

import type { JobDetail } from "@/lib/api";
import {
  FLAG_TEXT,
  LEVEL_LABELS,
  ROLE_LABELS,
  allLocations,
  daysSince,
  formatDate,
  formatSalary,
  pluralize,
  possessive,
} from "@/lib/format";

import { AgeStrip } from "./AgeStrip";
import { ApplyLink } from "./ApplyLink";
import { CompanyLogo } from "./CompanyLogo";
import { ExternalIcon, PinIcon, QuoteIcon } from "./Icons";
import { RiskBadge } from "./RiskBadge";
import { SaveButton } from "./SaveButton";

/*
  The pieces of a job's record, shared by the job page and the search page's
  preview pane so both always say the same thing.
*/

export function JobHeader({ job, titleAs = "h1", showPageLink = false }: { job: JobDetail; titleAs?: "h1" | "h2"; showPageLink?: boolean }) {
  const Title = titleAs;
  const places = allLocations(job.location);
  return (
    <header className="space-y-5">
      <div className="flex items-start gap-4">
        <CompanyLogo name={job.company} domain={job.company_domain} size="lg" />
        <div className="min-w-0 space-y-1">
          <Link href={`/companies/${job.company_slug}`} className="text-sm font-medium text-ink-soft hover:text-accent">
            {job.company}
          </Link>
          <Title
            className={`leading-tight font-semibold text-ink ${titleAs === "h1" ? "text-2xl sm:text-3xl" : "text-xl sm:text-2xl"}`}
          >
            {job.title}
          </Title>
        </div>
      </div>

      <ul className="flex flex-wrap gap-1.5">
        {job.salary && <li className="tag h-7 border-transparent bg-sunken px-2.5 text-[0.8125rem] text-ink">{formatSalary(job.salary)}</li>}
        <li className="tag h-7 max-w-full px-2.5 text-[0.8125rem]">
          <PinIcon className="size-3.5 shrink-0 text-ink-faint" />
          <span className="truncate">{places.length ? places.join(", ") : "Location not listed"}</span>
        </li>
        <li className="tag h-7 px-2.5 text-[0.8125rem]">{LEVEL_LABELS[job.level]}</li>
        {job.role_type !== "other" && <li className="tag h-7 px-2.5 text-[0.8125rem]">{ROLE_LABELS[job.role_type]}</li>}
        {(job.terms ?? []).map((term) => (
          <li key={term} className="tag h-7 px-2.5 text-[0.8125rem]">{term}</li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-3">
        {job.is_active ? (
          <ApplyLink
            job={{
              id: job.id,
              title: job.title,
              company: job.company,
              companyDomain: job.company_domain ?? null,
              location: job.location,
              url: job.url,
            }}
            className="btn btn-primary btn-lg"
          >
            Apply on {possessive(job.company)} site
            <ExternalIcon className="size-4" />
            <span className="sr-only"> (opens in a new tab)</span>
          </ApplyLink>
        ) : (
          <p className="inline-flex h-11 items-center rounded-lg bg-sunken px-4 text-sm font-medium text-ink-soft">
            This posting closed{job.closed_at ? ` on ${formatDate(job.closed_at)}` : ""}
          </p>
        )}
        <SaveButton
          variant="button"
          job={{
            id: job.id,
            title: job.title,
            company: job.company,
            companyDomain: job.company_domain ?? null,
            location: job.location,
            url: job.url,
          }}
        />
        {showPageLink && (
          <Link href={`/jobs/${job.id}`} className="link text-sm">
            Open full page
          </Link>
        )}
      </div>
    </header>
  );
}

function Evidence({ children }: { children: ReactNode }) {
  return (
    <blockquote className="mt-2 flex gap-2 rounded-lg bg-sunken px-3 py-2 text-sm text-ink">
      <QuoteIcon className="mt-0.5 size-4 shrink-0 text-ink-faint" />
      <span>
        {children}
        <span className="sr-only"> (quoted from the posting)</span>
      </span>
    </blockquote>
  );
}

function flagDetail(flag: string, job: JobDetail): ReactNode {
  const signals = job.signals;
  switch (flag) {
    case "not_existing_vacancy":
      return job.evidence.vacancy ? (
        <>
          <p className="text-ink-soft">The posting says so itself:</p>
          <Evidence>{job.evidence.vacancy}</Evidence>
        </>
      ) : (
        <p className="text-ink-soft">{FLAG_TEXT[flag]!.long}</p>
      );
    case "reposted": {
      const times = (signals.times_posted_before ?? 0) + 1;
      // describe what the history below shows: earlier listings may have come down, or still be up
      const earlierStillUp = job.posting_history.length > 0 && job.posting_history.every((p) => p.is_active);
      return (
        <p className="text-ink-soft">
          {times > 1
            ? earlierStillUp
              ? `Ghostless has seen this role posted ${pluralize(times, "time")} under separate listings, and the earlier one is still up.`
              : `Ghostless has seen this role posted ${pluralize(times, "time")}, taken down and put back up under a new listing.`
            : FLAG_TEXT[flag]!.long}
        </p>
      );
    }
    case "open_unusually_long":
      return (
        <p className="text-ink-soft">
          Up for {signals.age_known === false ? "at least " : ""}
          {pluralize(signals.days_open, "day")}
          {signals.typical_days_open
            ? `, while ${job.company} usually fills ${job.role_type === "other" ? "roles" : "these"} in ${pluralize(signals.typical_days_open, "day")}.`
            : ", far longer than most postings stay up."}
        </p>
      );
    default:
      return <p className="text-ink-soft">{FLAG_TEXT[flag]?.long}</p>;
  }
}

/** "SimplifyJobs/Summer2027-Internships" → its GitHub page; other names go to a search. */
function listUrl(name: string): string {
  return /^[\w.-]+\/[\w.-]+$/.test(name) ? `https://github.com/${name}` : `https://github.com/search?q=${encodeURIComponent(name)}`;
}

export function PostingRecord({ job, headingAs = "h2" }: { job: JobDetail; headingAs?: "h2" | "h3" }) {
  const Heading = headingAs;
  const flags = (job.signals.flags ?? []).filter((f) => FLAG_TEXT[f]);
  const sourceGap =
    job.source_posted_at && job.signals.age_known ? daysSince(job.first_seen) - daysSince(job.source_posted_at) : 0;

  return (
    <section aria-label="Posting record" className="record-box space-y-4">
      <div className="flex items-center justify-between gap-3">
        <Heading className="panel-title">Posting record</Heading>
        <RiskBadge risk={job.signals.risk} size="md" />
      </div>
      <AgeStrip signals={job.signals} company={job.company} isActive={job.is_active} />
      {job.listed_in && (
        <p className="text-sm text-ink-soft">
          Found in the{" "}
          <a href={listUrl(job.listed_in)} target="_blank" rel="noopener noreferrer" className="link">
            {job.listed_in}
          </a>{" "}
          list on GitHub, which links to {possessive(job.company)} own application page. Ghostless doesn&apos;t read{" "}
          {possessive(job.company)} job board yet, so it has only what the list shows: the title, places and season.
        </p>
      )}
      {job.signals.age_known === false && (
        <p className="text-sm text-ink-faint">
          This posting was already up when Ghostless started tracking {job.company}, so its true age is longer.
        </p>
      )}
      {sourceGap > 1 && (
        <p className="rounded-lg bg-ochre-tint px-3 py-2 text-sm text-ochre">
          {possessive(job.company)} site dates this posting {formatDate(job.source_posted_at!)}, but Ghostless first saw it{" "}
          {pluralize(sourceGap, "day")} earlier. The date on the site was refreshed.
        </p>
      )}
      {flags.length > 0 ? (
        <ul className="space-y-4 border-t border-line pt-4">
          {flags.map((flag) => (
            <li key={flag} className="border-l-2 border-brick pl-3 text-sm">
              <p className="font-semibold text-ink">{FLAG_TEXT[flag]!.short}</p>
              {flagDetail(flag, job)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="border-t border-line pt-4 text-sm text-ink-soft">
          No ghost signals. It hasn&apos;t been reposted, duplicated, or left up unusually long, and the posting doesn&apos;t
          say it&apos;s a talent pool.
        </p>
      )}
    </section>
  );
}

export function PostingHistory({ job, headingAs = "h2" }: { job: JobDetail; headingAs?: "h2" | "h3" }) {
  const Heading = headingAs;
  const history = [
    ...job.posting_history,
    { id: job.id, url: job.url, first_seen: job.first_seen, closed_at: job.closed_at, is_active: job.is_active },
  ].sort((a, b) => a.first_seen.localeCompare(b.first_seen));
  if (history.length < 2) return null;
  return (
    <section className="record-box">
      <Heading className="panel-title mb-3">Posted {pluralize(history.length, "time")}</Heading>
      <ol className="space-y-3 border-l border-line-strong pl-4 text-sm">
        {history.map((entry) => (
          <li key={entry.id} className="relative">
            <span
              aria-hidden="true"
              className={`absolute top-1.5 -left-[1.3rem] size-2 rounded-full ${entry.id === job.id ? "bg-accent-solid" : "bg-line-strong"}`}
            />
            <p className="font-medium text-ink">
              {formatDate(entry.first_seen)}
              {entry.id === job.id && <span className="font-normal text-ink-soft"> (this listing)</span>}
            </p>
            <p className="text-ink-soft">{entry.closed_at ? `Taken down ${formatDate(entry.closed_at)}` : "Still up"}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Row({ label, value, quote, note }: { label: string; value: string; quote?: string | null; note?: string }) {
  return (
    <div className="py-3 text-sm sm:grid sm:grid-cols-[7.5rem_1fr] sm:gap-3">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="min-w-0">
        <span className="font-medium text-ink">{value}</span>
        {quote && <Evidence>{quote}</Evidence>}
        {note && <span className="mt-0.5 block text-ink-faint">{note}</span>}
      </dd>
    </div>
  );
}

const NOT_IN_TEXT = "Not in the posting text Ghostless receives";

export function Disclosures({ job, headingAs = "h2" }: { job: JobDetail; headingAs?: "h2" | "h3" }) {
  const Heading = headingAs;
  const hasText = Boolean(job.description);
  return (
    <section className="record-box">
      <Heading className="panel-title">What the posting discloses</Heading>
      <dl className="divide-y divide-line">
        <Row
          label="Pay"
          value={job.salary ? formatSalary(job.salary) : NOT_IN_TEXT}
          quote={job.evidence.salary}
          note={
            job.salary
              ? undefined
              : "Some employers add pay only on their own site. Check the original posting before you rule it out."
          }
        />
        <Row
          label="Real vacancy"
          value={
            job.vacancy === "existing"
              ? "Yes, an existing vacancy"
              : job.vacancy === "not_existing"
                ? "No, not a current vacancy"
                : hasText
                  ? "Not stated"
                  : NOT_IN_TEXT
          }
          quote={job.evidence.vacancy}
          note={job.vacancy ? undefined : "Ontario requires this in postings from employers with 25 or more staff."}
        />
        <Row
          label="AI screening"
          value={
            job.ai_screening === true
              ? "Uses AI to screen applicants"
              : job.ai_screening === false
                ? "No AI screening"
                : hasText
                  ? "Not stated"
                  : NOT_IN_TEXT
          }
          quote={job.evidence.ai_screening}
        />
        <Row label="First seen" value={formatDate(job.first_seen)} />
        <Row label="Last checked" value={formatDate(job.last_seen)} />
      </dl>
    </section>
  );
}

/* ---------- Description ---------- */

type Block = { kind: "heading" | "paragraph"; text: string } | { kind: "list"; items: string[] };

const BULLET = /^[•\-*]\s+/;

/** Turn stored description text (paragraphs and "• " bullets) into blocks. */
export function descriptionBlocks(text: string): Block[] {
  if (!text.includes("\n")) {
    // stored before structure was kept: group sentences into short paragraphs
    const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z])/);
    const blocks: Block[] = [];
    for (let i = 0; i < sentences.length; i += 4) {
      blocks.push({ kind: "paragraph", text: sentences.slice(i, i + 4).join(" ") });
    }
    return blocks;
  }
  const blocks: Block[] = [];
  for (const chunk of text.split(/\n{2,}/)) {
    const lines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    let items: string[] = [];
    const flush = () => {
      if (items.length) blocks.push({ kind: "list", items });
      items = [];
    };
    lines.forEach((line, i) => {
      if (BULLET.test(line)) {
        items.push(line.replace(BULLET, ""));
        return;
      }
      flush();
      const isHeading = line.length <= 70 && !/[.!?:;,]$/.test(line) && i < lines.length - 1;
      const looksLikeHeading = isHeading || (line.length <= 70 && line.endsWith(":") && i < lines.length - 1);
      blocks.push({ kind: looksLikeHeading ? "heading" : "paragraph", text: line.replace(/:$/, "") });
    });
    flush();
  }
  return blocks;
}

export function JobDescription({ job, headingAs = "h2" }: { job: JobDetail; headingAs?: "h2" | "h3" }) {
  const Heading = headingAs;
  const Sub = headingAs === "h2" ? "h3" : "h4";
  return (
    <section>
      <Heading className="panel-title mb-3">Job description</Heading>
      {job.description ? (
        <div className="max-w-[68ch] space-y-3 leading-relaxed text-ink-soft">
          {descriptionBlocks(job.description).map((block, i) =>
            block.kind === "heading" ? (
              <Sub key={i} className="pt-2 font-sans text-base font-semibold tracking-normal text-ink">
                {block.text}
              </Sub>
            ) : block.kind === "list" ? (
              <ul key={i} className="list-disc space-y-1.5 pl-5 marker:text-line-strong">
                {block.items.map((item, j) => (
                  <li key={j}>{item}</li>
                ))}
              </ul>
            ) : (
              <p key={i}>{block.text}</p>
            ),
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-line-strong p-5 text-sm text-ink-soft in-data-flat:p-4">
          <p>
            {job.listed_in
              ? "This posting comes from a public job list, which doesn't include descriptions. Read it on the employer's site."
              : "Ghostless hasn't loaded this posting's description yet. Large employers' descriptions are fetched a batch at a time, so it should appear within a few daily runs."}
          </p>
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="link mt-2 inline-flex items-center gap-1"
          >
            Read it on {possessive(job.company)} site
            <ExternalIcon className="size-3.5" />
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </div>
      )}
    </section>
  );
}

export function SkillChips({ skills, headingAs = "h2" }: { skills: string[]; headingAs?: "h2" | "h3" }) {
  const Heading = headingAs;
  if (!skills.length) return null;
  return (
    <section>
      <Heading className="panel-title mb-3">Skills mentioned</Heading>
      <ul className="flex flex-wrap gap-1.5">
        {skills.map((skill) => (
          <li key={skill}>
            <Link
              href={`/jobs?skill=${encodeURIComponent(skill)}`}
              className="tag h-7 px-2.5 text-[0.8125rem] text-ink transition-colors hover:border-accent hover:text-accent"
            >
              {skill}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
