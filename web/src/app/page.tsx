import Link from "next/link";
import { connection } from "next/server";

import { AgeStrip } from "@/components/AgeStrip";
import { CompanyLogo } from "@/components/CompanyLogo";
import { SearchIcon } from "@/components/Icons";
import { JobList } from "@/components/JobCard";
import { RiskBadge } from "@/components/RiskBadge";
import { Stat } from "@/components/Stat";
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
      <section className="border-b border-line bg-surface text-ink">
        <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 pt-12 pb-24 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pt-16 lg:pb-32">
          <div className="space-y-7">
            {updated && (
              <p className="inline-flex items-center gap-2 rounded-full border border-line-strong px-3 py-1 text-sm text-ink-soft">
                <span aria-hidden="true" className="size-2 rounded-full bg-accent" />
                Updated {updated} from {pluralize(stats.companies, "employer")}&apos; career sites
              </p>
            )}
            <h1 className="max-w-xl text-5xl font-semibold tracking-tight text-ink sm:text-6xl">
              Apply where they&apos;re actually hiring.
            </h1>
            <p className="max-w-lg text-lg text-ink-soft">
              Ghostless keeps the record job boards don&apos;t: how long each tech role has really been open, whether it was
              quietly reposted, and whether the employer says it&apos;s a real opening.
            </p>
            <form action="/jobs" method="get" role="search" className="flex max-w-xl gap-2">
              <label htmlFor="home-q" className="sr-only">
                Search jobs
              </label>
              <div className="relative min-w-0 flex-1">
                <SearchIcon className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-ink-faint" />
                <input
                  id="home-q"
                  type="search"
                  name="q"
                  maxLength={100}
                  placeholder="Software intern, Shopify, Python..."
                  autoComplete="off"
                  className="h-13 w-full rounded-xl border border-line-strong bg-surface pr-3 pl-12 text-lg text-ink placeholder:text-ink-faint focus:ring-2 focus:ring-accent/30 focus:outline-none"
                />
              </div>
              <button
                type="submit"
                className="h-13 shrink-0 rounded-xl bg-accent px-6 font-semibold text-on-accent transition-opacity hover:opacity-90"
              >
                Search
              </button>
            </form>
            <ul className="flex flex-wrap gap-2" aria-label="Popular searches">
              {QUICK_LINKS.map(({ label, href }) => (
                <li key={label}>
                  <Link
                    href={href}
                    className="inline-block rounded-full border border-line-strong px-3.5 py-1.5 text-sm text-ink-soft transition-colors hover:border-accent hover:text-ink"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {exhibit ? (
            <figure className="rounded-2xl bg-sunken p-3 ring-1 ring-line">
              <figcaption className="px-3 pt-2 pb-3 text-sm text-ink-soft">
                A real posting from today&apos;s data, and why it&apos;s flagged
              </figcaption>
              <div className="space-y-4 rounded-xl bg-surface p-5 text-ink shadow-pop">
                <div className="flex items-start gap-3">
                  <CompanyLogo name={exhibit.company} domain={exhibit.company_domain} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink-soft">{exhibit.company}</p>
                    <p className="font-display text-xl leading-snug font-semibold">{exhibit.title}</p>
                  </div>
                  <RiskBadge risk={exhibit.signals.risk} />
                </div>
                <AgeStrip signals={exhibit.signals} company={exhibit.company} />
                <ul className="space-y-2.5 border-t border-line pt-4">
                  {(exhibit.signals.flags ?? []).map((flag) => (
                    <li key={flag} className="border-l-2 border-brick pl-3 text-sm">
                      <span className="font-semibold">{FLAG_TEXT[flag]?.short}.</span>{" "}
                      <span className="text-ink-soft">{FLAG_TEXT[flag]?.long}</span>
                    </li>
                  ))}
                </ul>
                <Link href={`/jobs/${exhibit.id}`} className="inline-block text-sm font-medium text-accent hover:underline">
                  See this posting&apos;s full record
                </Link>
              </div>
            </figure>
          ) : (
            <div className="rounded-2xl bg-sunken p-6 ring-1 ring-line">
              <p className="font-display text-xl font-semibold">No high-risk postings right now.</p>
              <p className="mt-2 text-sm text-ink-soft">
                Ghost signals build up as Ghostless watches postings over time. Check back after a few daily runs.
              </p>
            </div>
          )}
        </div>
      </section>

      <div className="mx-auto -mt-12 max-w-7xl px-4 sm:px-6">
        <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
        </dl>
      </div>

      <section className="mx-auto max-w-7xl px-4 pt-16 sm:px-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-3xl font-semibold text-ink">New this week for students</h2>
            <p className="text-ink-soft">Internships, co-ops and new grad roles in Canada or remote, first seen in the last 7 days.</p>
          </div>
          <Link href={preset(STUDENT_FILTERS)} className="text-sm font-medium text-accent hover:underline">
            See all {fresh.total.toLocaleString("en-CA")}
          </Link>
        </div>
        {fresh.items.length ? (
          <div className="[&>ul]:grid [&>ul]:gap-3 [&>ul]:space-y-0 md:[&>ul]:grid-cols-2 xl:[&>ul]:grid-cols-3 [&_article]:h-full [&>ul>li]:h-full">
            <JobList jobs={fresh.items} headingLevel="h3" />
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-line-strong bg-surface p-6 text-sm text-ink-soft">
            No new student roles in the last week.{" "}
            <Link href={preset({ level: ["intern", "new_grad"] })} className="font-medium text-accent hover:underline">
              See all student roles
            </Link>
            .
          </p>
        )}
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-4 pt-16 sm:px-6 lg:grid-cols-[1fr_1.3fr]">
        <div className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
          <div className="mb-4 flex items-baseline justify-between gap-3">
            <h2 className="font-sans text-base font-semibold text-ink">Hiring the most this week</h2>
            <Link href="/companies?sort=new" className="text-sm font-medium text-accent hover:underline">
              All companies
            </Link>
          </div>
          {hiring.length ? (
            <ol className="divide-y divide-line">
              {hiring.map((c) => (
                <li key={c.slug} className="flex items-center gap-3 py-3">
                  <CompanyLogo name={c.name} domain={c.domain} size="sm" />
                  <Link href={`/companies/${c.slug}`} className="min-w-0 flex-1 truncate font-medium text-ink hover:text-accent hover:underline">
                    {c.name}
                  </Link>
                  <span className="text-sm text-ink-soft">
                    <span className="font-semibold text-ink">{c.new_last_7_days}</span> new
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-ink-soft">No new postings this week yet.</p>
          )}
        </div>
        <div className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
          <h2 className="sr-only">Hiring trend</h2>
          <WeeklyChart weeks={weekly} title="Tech postings opened and closed, last 12 weeks" />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 pt-16 sm:px-6">
        <div className="grid gap-10 rounded-2xl border border-line bg-surface p-6 text-ink sm:p-10 lg:grid-cols-[1fr_2fr]">
          <div className="space-y-3">
            <h2 className="text-3xl font-semibold">Four signals, all from the public record</h2>
            <p className="text-ink-soft">
              Each flag is evidence, not a verdict. A long-open role can be genuinely hard to fill. Ghostless shows you the
              record and quotes the posting, so you decide where your time goes.
            </p>
            <Link href="/how-it-works" className="inline-block font-medium text-accent hover:underline">
              How the signals are calculated
            </Link>
          </div>
          <dl className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
            {Object.entries(FLAG_TEXT).map(([key, flag]) => (
              <div key={key} className="rounded-xl bg-sunken p-5 ring-1 ring-line">
                <dt className="font-semibold">{flag.short}</dt>
                <dd className="mt-1 text-sm text-ink-soft">{flag.long}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </>
  );
}
