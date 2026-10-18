import Link from "next/link";
import { connection } from "next/server";

import { AgeStrip } from "@/components/AgeStrip";
import { CompanyLogo } from "@/components/CompanyLogo";
import { SearchIcon } from "@/components/Icons";
import { JobList } from "@/components/JobCard";
import { RiskBadge } from "@/components/RiskBadge";
import { Stat, StatStrip } from "@/components/Stat";
import { WeeklyChart } from "@/components/WeeklyChart";
import { type Job, api } from "@/lib/api";
import { EMPTY_FILTERS, type JobFilters, jobsHref } from "@/lib/filters";
import { FLAG_TEXT, ago, percent, pluralize } from "@/lib/format";

/** The most telling high-risk posting: several flags, and an exact age if possible. */
function pickExhibit(jobs: Job[]): Job | undefined {
  return [...jobs].sort((a, b) => {
    const score = (j: Job) => (j.signals.flags?.length ?? 0) * 100 + (j.signals.age_known ? 50 : 0) + j.signals.days_open;
    return score(b) - score(a);
  })[0];
}

const preset = (changes: Partial<JobFilters>) => jobsHref({ ...EMPTY_FILTERS, ...changes });

const STUDENT_FILTERS: Partial<JobFilters> = {
  level: ["intern", "new_grad"],
  location: "canada_or_remote",
  newWithinDays: 7,
};

const QUICK_LINKS = [
  { label: "Internships and co-ops", href: preset({ level: ["intern"] }) },
  { label: "New grad", href: preset({ level: ["new_grad"] }) },
  { label: "Remote", href: preset({ location: "remote" }) },
  { label: "In Canada", href: preset({ location: "canada" }) },
  { label: "Shows pay", href: preset({ hasSalary: true }) },
];

/** A section heading with an optional link at the end of the row. */
function SectionHead({ title, lead, action }: { title: string; lead?: string; action?: { href: string; label: string } }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div>
        <h2 className="text-2xl font-semibold text-ink">{title}</h2>
        {lead && <p className="mt-1 max-w-2xl text-sm text-ink-soft">{lead}</p>}
      </div>
      {action && (
        <Link href={action.href} className="link text-sm">
          {action.label}
        </Link>
      )}
    </div>
  );
}

export default async function HomePage() {
  await connection();
  const [stats, highRisk, fresh, companies, weekly] = await Promise.all([
    api.stats(),
    api.jobs({ risk: ["high"], role: ["sde", "data_eng", "data"], sort: "oldest", limit: 20 }),
    api.jobs({ level: ["intern", "new_grad"], location: "canada_or_remote", new_within_days: 7, limit: 6 }),
    api.companies(),
    api.weekly(12),
  ]);
  const exhibit = pickExhibit(highRisk.items);
  const hiring = [...companies]
    .filter((c) => c.new_last_7_days > 0)
    .sort((a, b) => b.new_last_7_days - a.new_last_7_days)
    .slice(0, 6);
  const updated = stats.last_run ? ago(stats.last_run.finished_at ?? stats.last_run.started_at) : null;

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="grid items-center gap-10 pt-12 pb-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:pt-20 lg:pb-16">
            <div>
              {updated && (
                <p className="mb-6 inline-flex items-center gap-2 text-sm text-ink-soft">
                  <span aria-hidden="true" className="relative flex size-2">
                    <span className="absolute inset-0 rounded-full bg-good opacity-40" />
                    <span className="relative m-auto size-1.5 rounded-full bg-good" />
                  </span>
                  Updated {updated}
                  <span aria-hidden="true" className="text-ink-faint">
                    ·
                  </span>
                  {pluralize(stats.companies, "employer")} tracked
                </p>
              )}
              <h1 className="max-w-xl text-5xl font-semibold tracking-[-0.03em] text-ink sm:text-6xl">
                Apply where they&apos;re actually hiring.
              </h1>
              <p className="mt-5 max-w-lg text-lg text-ink-soft">
                Ghostless keeps the record job boards don&apos;t: how long each tech role has really been open, whether it was
                quietly reposted, and whether the employer says it&apos;s a real opening.
              </p>
              <form action="/jobs" method="get" role="search" className="mt-8 flex max-w-xl gap-2">
                <label htmlFor="home-q" className="sr-only">
                  Search jobs
                </label>
                <div className="relative min-w-0 flex-1">
                  <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 size-4.5 -translate-y-1/2 text-ink-faint" />
                  <input
                    id="home-q"
                    type="search"
                    name="q"
                    maxLength={100}
                    placeholder="Software intern, Shopify, Python..."
                    autoComplete="off"
                    className="field field-lg pl-10"
                  />
                </div>
                <button type="submit" className="btn btn-primary btn-lg">
                  Search
                </button>
              </form>
              <div className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-2 text-sm">
                <span className="mr-1 text-ink-faint">Popular</span>
                <ul className="contents" aria-label="Popular searches">
                  {QUICK_LINKS.map(({ label, href }) => (
                    <li key={label}>
                      <Link href={href} className="btn btn-ghost btn-sm h-7 px-2.5 text-ink-soft">
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {exhibit ? (
              <figure className="panel overflow-hidden shadow-pop">
                <figcaption className="flex items-center justify-between gap-3 border-b border-line bg-sunken/50 px-5 py-2.5 text-xs text-ink-soft">
                  <span className="font-medium text-ink">Posting record</span>
                  <span>A real posting from today&apos;s data</span>
                </figcaption>
                <div className="space-y-5 p-5">
                  <div className="flex items-start gap-3">
                    <CompanyLogo name={exhibit.company} domain={exhibit.company_domain} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-sm text-ink-soft">{exhibit.company}</p>
                        <RiskBadge risk={exhibit.signals.risk} />
                      </div>
                      <p className="mt-0.5 font-display text-lg leading-snug font-semibold tracking-tight text-ink">{exhibit.title}</p>
                    </div>
                  </div>
                  <AgeStrip signals={exhibit.signals} company={exhibit.company} />
                  <ul className="space-y-3 border-t border-line pt-4">
                    {(exhibit.signals.flags ?? []).map((flag) => (
                      <li key={flag} className="flex gap-3 text-sm">
                        <span aria-hidden="true" className="mt-1.5 h-3 w-0.5 shrink-0 rounded-full bg-brick" />
                        <span>
                          <span className="font-semibold text-ink">{FLAG_TEXT[flag]?.short}.</span>{" "}
                          <span className="text-ink-soft">{FLAG_TEXT[flag]?.long}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <Link href={`/jobs/${exhibit.id}`} className="link inline-block text-sm">
                    See this posting&apos;s full record
                  </Link>
                </div>
              </figure>
            ) : (
              <div className="panel p-6">
                <p className="font-display text-xl font-semibold">No high-risk postings right now.</p>
                <p className="mt-2 text-sm text-ink-soft">
                  Ghost signals build up as Ghostless watches postings over time. Check back after a few daily runs.
                </p>
              </div>
            )}
          </div>

          <StatStrip className="mb-12 lg:mb-16">
            <Stat label="Open tech roles" value={stats.tech_active_jobs.toLocaleString("en-CA")} note={`at ${pluralize(stats.companies, "employer")}`} />
            <Stat label="First seen this week" value={stats.tech_new_last_7_days.toLocaleString("en-CA")} note="genuinely new, not reposted dates" />
            <Stat
              label="High ghost risk"
              value={percent(stats.tech_high_risk_active_jobs, stats.tech_active_jobs)}
              note={`${pluralize(stats.tech_high_risk_active_jobs, "open posting")}`}
            />
            <Stat
              label="Show their pay"
              value={percent(stats.tech_with_salary_active_jobs, stats.tech_active_jobs)}
              note="in the posting text"
            />
          </StatStrip>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 pt-14 sm:px-6">
        <SectionHead
          title="New this week for students"
          lead="Internships, co-ops and new grad roles in Canada or remote, first seen in the last 7 days."
          action={{ href: preset(STUDENT_FILTERS), label: `See all ${fresh.total.toLocaleString("en-CA")}` }}
        />
        {fresh.items.length ? (
          <JobList jobs={fresh.items} headingLevel="h3" columns={2} />
        ) : (
          <p className="panel border-dashed p-6 text-sm text-ink-soft">
            No new student roles in the last week.{" "}
            <Link href={preset({ level: ["intern", "new_grad"] })} className="link">
              See all student roles
            </Link>
            .
          </p>
        )}
      </section>

      <section className="mx-auto grid max-w-7xl items-start gap-5 px-4 pt-14 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
        <div className="panel">
          <div className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
            <h2 className="panel-title">
              Hiring the most this week <span className="font-normal text-ink-faint">· new postings, all roles</span>
            </h2>
            <Link href="/companies?sort=new" className="link shrink-0 text-sm">
              All companies
            </Link>
          </div>
          {hiring.length ? (
            <ol className="divide-y divide-line">
              {hiring.map((c, i) => (
                <li key={c.slug} className="flex items-center gap-3 px-5 py-2.5">
                  <span className="w-4 text-right text-xs text-ink-faint tabular-nums">{i + 1}</span>
                  <CompanyLogo name={c.name} domain={c.domain} size="sm" />
                  <Link href={`/companies/${c.slug}`} className="min-w-0 flex-1 truncate text-sm font-medium text-ink hover:text-accent">
                    {c.name}
                  </Link>
                  <span className="text-sm text-ink-soft tabular-nums">
                    <span className="font-semibold text-ink">{c.new_last_7_days.toLocaleString("en-CA")}</span> new
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="px-5 py-4 text-sm text-ink-soft">No new postings this week yet.</p>
          )}
        </div>
        <div className="panel p-5">
          <h2 className="sr-only">Hiring trend</h2>
          <WeeklyChart weeks={weekly} title="Tech postings opened and closed, last 12 weeks" />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 pt-14 sm:px-6">
        <SectionHead
          title="Four signals, all from the public record"
          lead="Each flag is evidence, not a verdict. A long-open role can be genuinely hard to fill. Ghostless shows you the record and quotes the posting, so you decide where your time goes."
          action={{ href: "/how-it-works", label: "How the signals are calculated" }}
        />
        <dl className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(FLAG_TEXT).map(([key, flag]) => (
            <div key={key} className="bg-surface p-5">
              <dt className="text-sm font-semibold text-ink">{flag.short}</dt>
              <dd className="mt-1.5 text-sm text-ink-soft">{flag.long}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
