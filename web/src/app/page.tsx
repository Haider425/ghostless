import Link from "next/link";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { AgeStrip, ageSentence } from "@/components/AgeStrip";
import { HomeSearch } from "@/components/HomeSearch";
import { CheckIcon, ClockIcon, CrossIcon } from "@/components/Icons";
import { JobList } from "@/components/JobCard";
import { Ring } from "@/components/Match";
import { RiskBadge } from "@/components/RiskBadge";
import { type Job, api } from "@/lib/api";
import { EMPTY_FILTERS, type JobFilters, jobsHref } from "@/lib/filters";
import { FLAG_TEXT, ago, percent, pluralize } from "@/lib/format";

/*
  Home: get people searching, and show why Ghostless is different. The
  search, one real posting's record as proof, three figures from today's
  data, three short reasons, and one call to action.
*/

/** The most telling high-risk posting: several flags, and an exact age if possible. */
function pickExhibit(jobs: Job[]): Job | undefined {
  return [...jobs].sort((a, b) => {
    const score = (j: Job) => (j.signals.flags?.length ?? 0) * 100 + (j.signals.age_known ? 50 : 0) + j.signals.days_open;
    return score(b) - score(a);
  })[0];
}

const preset = (changes: Partial<JobFilters>) => jobsHref({ ...EMPTY_FILTERS, ...changes });

const QUICK_LINKS = [
  { label: "Internships and co-ops", href: preset({ level: ["intern"] }) },
  { label: "New grad", href: preset({ level: ["new_grad"] }) },
  { label: "Remote", href: preset({ location: "remote" }) },
  { label: "In Canada", href: preset({ location: "canada" }) },
  { label: "Shows pay", href: preset({ hasSalary: true }) },
];

function Exhibit({ job }: { job: Job }) {
  const flags = (job.signals.flags ?? []).filter((f) => FLAG_TEXT[f]);
  const bar = job.signals.risk === "high" ? "bg-brick" : "bg-ochre";
  return (
    <div className="space-y-4 p-6 sm:p-8">
      <div className="flex items-center justify-between gap-3">
        <p className="panel-title text-ink-soft">Posting record</p>
        <RiskBadge risk={job.signals.risk} />
      </div>
      <p className="text-ui text-ink">
        <span className="font-semibold">{job.title}</span> <span className="text-ink-soft">at {job.company}</span>
      </p>
      <AgeStrip signals={job.signals} company={job.company} />
      {flags.length > 0 && (
        <ul className="space-y-3">
          {flags.map((flag) => (
            <li key={flag} className="flex gap-3 text-ui">
              <span aria-hidden="true" className={`w-[3px] shrink-0 rounded-full ${bar}`} />
              <span>
                <span className="font-semibold text-ink">{FLAG_TEXT[flag]?.short}.</span>{" "}
                <span className="text-ink-soft">{FLAG_TEXT[flag]?.long}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link href={`/jobs/${job.id}`} className="link inline-block text-ui">
        See this posting&apos;s full record
      </Link>
    </div>
  );
}

function Reason({ label, title, body, children }: { label: string; title: string; body: string; children: ReactNode }) {
  return (
    <div className="card flex flex-col p-7">
      <p className="text-ui font-medium text-ink-soft">{label}</p>
      <h3 className="mt-2 text-2xl font-bold tracking-[-0.015em] text-ink">{title}</h3>
      <p className="mt-2.5 text-base text-ink-soft">{body}</p>
      <div className="mt-auto pt-6">{children}</div>
    </div>
  );
}

export default async function HomePage() {
  await connection();
  const [stats, highRisk, fresh] = await Promise.all([
    api.stats(),
    api.jobs({ risk: ["high"], role: ["sde", "data_eng", "data"], sort: "oldest", limit: 20 }),
    api.jobs({ level: ["intern", "new_grad"], location: "canada_or_remote", new_within_days: 7, limit: 2 }),
  ]);
  const exhibit = pickExhibit(highRisk.items);
  const updated = stats.last_run ? ago(stats.last_run.finished_at ?? stats.last_run.started_at) : null;
  const openRoles = stats.tech_active_jobs.toLocaleString("en-CA");
  const rows = [...(exhibit ? [exhibit] : []), ...fresh.items].slice(0, 3);

  return (
    <div className="px-4 sm:px-6 lg:px-10">
      <section className="mx-auto flex max-w-4xl flex-col items-center pt-14 pb-10 text-center sm:pt-24">
        {updated && (
          <p className="inline-flex items-center gap-2 rounded-full bg-sunken px-3.5 py-1.5 text-sm font-medium text-ink-soft">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-accent-solid" />
            Updated {updated} · {pluralize(stats.companies, "employer")} tracked
          </p>
        )}
        <h1 className="mt-6 text-5xl leading-[1.05] font-bold tracking-[-0.04em] text-ink sm:text-7xl sm:leading-[1.05]">
          Apply where they&apos;re actually hiring.
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-ink-soft sm:text-xl sm:leading-[1.9rem]">
          Tech jobs in Canada with the record job boards don&apos;t keep: when each role really opened, whether it was quietly
          reposted, and whether it&apos;s a real opening.
        </p>
        <HomeSearch />
        <ul className="mt-5 flex flex-wrap items-center justify-center gap-2" aria-label="Popular searches">
          <li aria-hidden="true" className="mr-1 text-ui text-ink-faint">
            Popular:
          </li>
          {QUICK_LINKS.map(({ label, href }) => (
            <li key={label}>
              <Link href={href} className="inline-flex h-9 items-center rounded-full border border-line px-3.5 text-ui font-medium text-ink hover:bg-sunken">
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="From today's data" className="mx-auto max-w-280 pt-10">
        <p className="mb-3 text-center text-sm text-ink-faint">A real posting from today&apos;s data</p>
        {exhibit ? (
          <div className="panel overflow-hidden shadow-pop lg:grid lg:grid-cols-[29rem_minmax(0,1fr)]">
            <div className="border-b border-line p-2 lg:border-r lg:border-b-0">
              <JobList jobs={rows} headingLevel="h3" bare selectedId={exhibit.id} />
            </div>
            <Exhibit job={exhibit} />
          </div>
        ) : (
          <div className="card p-6 text-center">
            <p className="font-semibold text-ink">No high-risk postings right now.</p>
            <p className="mt-1 text-ui text-ink-soft">Ghost signals build up as Ghostless watches postings over time.</p>
          </div>
        )}
      </section>

      <dl className="mx-auto mt-14 grid max-w-3xl grid-cols-3 gap-6 text-center">
        {[
          { value: openRoles, label: "open tech roles" },
          { value: stats.tech_new_last_7_days.toLocaleString("en-CA"), label: "first seen this week" },
          { value: percent(stats.tech_high_risk_active_jobs, stats.tech_active_jobs), label: "flagged high ghost risk" },
        ].map(({ value, label }) => (
          <div key={label} className="flex flex-col-reverse">
            <dt className="mt-1 text-sm text-ink-soft sm:text-base">{label}</dt>
            <dd className="text-3xl font-bold tracking-[-0.03em] text-ink sm:text-5xl">{value}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="why" className="mx-auto max-w-280 pt-24">
        <h2 id="why" className="text-center text-4xl font-bold tracking-[-0.03em] text-ink sm:text-5xl">
          What job boards don&apos;t tell you.
        </h2>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <Reason label="True age" title="The day it really opened." body="Ghostless records the day it first sees a posting. A repost can't reset it.">
            {exhibit && (
              <p className="flex items-center gap-2 rounded-xl bg-surface px-3.5 py-3 text-ui font-medium text-ink">
                <ClockIcon className="size-4.5 text-ink-soft" />
                {ageSentence(exhibit.signals)}
              </p>
            )}
          </Reason>
          <Reason
            label="Ghost signals"
            title="Evidence, not a verdict."
            body="Reposts, duplicates, roles left up for months, and postings that say they aren't a real vacancy, quoted."
          >
            <div className="flex flex-wrap gap-2">
              <RiskBadge risk="high" />
              <RiskBadge risk="medium" />
            </div>
          </Reason>
          <Reason
            label="Resume match"
            title="A score that explains itself."
            body="Every requirement marked as met or missing, with what to change before you apply."
          >
            <div className="flex items-center gap-3 rounded-xl bg-surface px-3.5 py-3">
              <Ring score={82} size="sm" />
              <div className="text-sm">
                <p className="flex flex-wrap items-center gap-x-1.5 font-medium text-ink">
                  <CheckIcon className="size-4 text-accent" /> Python
                  <CheckIcon className="ml-1 size-4 text-accent" /> SQL
                  <CrossIcon className="ml-1 size-4 text-ink-faint" /> Kafka
                </p>
                <p className="text-ink-faint">Example</p>
              </div>
            </div>
          </Reason>
        </div>
        <p className="mt-6 text-center">
          <Link href="/how-it-works" className="link text-ui">
            How the signals are calculated
          </Link>
        </p>
      </section>

      <section className="mx-auto flex max-w-3xl flex-col items-center py-28 text-center">
        <h2 className="text-4xl font-bold tracking-[-0.03em] text-ink sm:text-5xl">Spend your time on roles that are really open.</h2>
        <Link href={jobsHref(EMPTY_FILTERS)} className="btn btn-primary btn-lg mt-8">
          Search {openRoles} open tech roles
        </Link>
      </section>
    </div>
  );
}
