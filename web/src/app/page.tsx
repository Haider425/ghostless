import Link from "next/link";
import { connection } from "next/server";
import type { CSSProperties, ReactNode } from "react";

import { ageSentence } from "@/components/AgeStrip";
import { CompanyLogo } from "@/components/CompanyLogo";
import { GhostMascot, MiniGhost } from "@/components/GhostMascot";
import { HomeSearch } from "@/components/HomeSearch";
import { CheckIcon, CrossIcon } from "@/components/Icons";
import { Ring } from "@/components/Match";
import { Reveal } from "@/components/Reveal";
import { RiskBadge } from "@/components/RiskBadge";
import { type Job, type JobDetail, api } from "@/lib/api";
import { EMPTY_FILTERS, type JobFilters, jobsHref } from "@/lib/filters";
import { FLAG_TEXT, ago, formatDate, percent, pluralize, shortLocation } from "@/lib/format";

/*
  Home (brand direction B): a friendly ghost checks a real high-risk posting
  from today's data while handwritten notes explain what it found; a live
  ticker of today's numbers; three reasons; one call to action. Every number,
  note and quote comes from the data. The motion plays once and is off for
  reduced motion (globals.css).
*/

/** The most telling high-risk posting: several flags, a quote, and an exact age if possible. */
function pickExhibit(jobs: Job[]): Job | undefined {
  return [...jobs].sort((a, b) => {
    const score = (j: Job) =>
      (j.signals.flags?.length ?? 0) * 100 +
      (j.signals.flags?.includes("not_existing_vacancy") ? 80 : 0) +
      (j.signals.age_known ? 50 : 0) +
      j.signals.days_open;
    return score(b) - score(a);
  })[0];
}

const preset = (changes: Partial<JobFilters>) => jobsHref({ ...EMPTY_FILTERS, ...changes });

const QUICK_LINKS = [
  { label: "Internships and co-ops", href: preset({ level: ["intern"] }), tint: "bg-b-blush", dot: "bg-[#e8735a]" },
  { label: "New grad", href: preset({ level: ["new_grad"] }), tint: "bg-b-mint", dot: "bg-[#3ba765]" },
  { label: "Remote", href: preset({ location: "remote" }), tint: "bg-b-lilac", dot: "bg-[#7c6be8]" },
  { label: "In Canada", href: preset({ location: "canada" }), tint: "bg-b-butter", dot: "bg-[#e0a800]" },
  { label: "Shows pay", href: preset({ hasSalary: true }), tint: "bg-b-sky", dot: "bg-accent-solid" },
];

const delay = (seconds: number) => ({ "--d": `${seconds}s` }) as CSSProperties;

/** A handwritten note with an arrow that draws itself in. Desktop only: on phones the card speaks for itself. */
function Note({ children, className, arrow, arrowClass, at }: { children: ReactNode; className: string; arrow: string; arrowClass: string; at: number }) {
  return (
    <>
      <p aria-hidden="true" className={`hx-note absolute hidden font-hand text-[1.65rem] leading-[1.05] whitespace-pre-line text-b-ink md:block ${className}`} style={delay(at)}>
        {children}
      </p>
      <svg aria-hidden="true" viewBox="0 0 100 60" fill="none" className={`hx-arrow absolute hidden h-[60px] w-[100px] text-b-ink md:block ${arrowClass}`}>
        <path d={arrow} stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={delay(at + 0.35)} />
      </svg>
    </>
  );
}

function flagNote(flags: string[], hasQuote: boolean): string | null {
  if (flags.includes("reposted")) return "taken down, then\nput back up";
  if (flags.includes("duplicate_posting")) return "same role,\nlisted twice";
  if (flags.includes("open_unusually_long")) return "way past their\nusual time";
  if (flags.includes("not_existing_vacancy") && !hasQuote) return "not a real\nvacancy";
  return null;
}

function Exhibit({ job, detail }: { job: Job; detail: JobDetail | null }) {
  const flags = (job.signals.flags ?? []).filter((f) => FLAG_TEXT[f]);
  const quote = detail?.evidence?.vacancy ?? null;
  const typical = job.signals.typical_days_open ?? null;
  const high = job.signals.risk === "high";
  const overdue = typical !== null && job.signals.days_open > typical;
  const fNote = flagNote(flags, Boolean(quote));
  return (
    <div className="relative mx-auto max-w-[64rem] pt-6 pb-16 md:pt-14 md:pb-24">
      <article className="hx-card relative mx-auto w-full max-w-[34rem] rounded-[1.75rem] border border-b-line bg-b-card p-5 text-left shadow-brand sm:p-7">
        <div className="flex items-start gap-3.5 pr-28 sm:pr-36">
          <CompanyLogo name={job.company} domain={job.company_domain} />
          <div className="min-w-0">
            <h3 className="font-brand text-[1.35rem] leading-tight font-bold tracking-[-0.02em] text-b-ink">{job.title}</h3>
            <p className="mt-0.5 font-friendly text-sm font-medium text-b-soft">
              {job.company} · {shortLocation(job.location)}
            </p>
          </div>
        </div>
        <p
          className={`hx-stamp absolute top-5 right-5 rotate-8 rounded-lg border-2 px-2.5 py-1 font-brand text-[0.8rem] font-extrabold tracking-[0.12em] uppercase sm:top-7 sm:right-7 ${
            high ? "border-b-red text-b-red" : "border-ochre text-ochre"
          }`}
        >
          {high ? "High ghost risk" : "Some flags"}
        </p>

        <ul className="mt-5 flex flex-wrap gap-2 font-friendly text-[0.8125rem] font-semibold" aria-label="What Ghostless found">
          <li className={`hx-pop rounded-full px-3 py-1.5 ${overdue || !job.signals.age_known ? "bg-b-blush text-b-red" : "bg-b-paper text-b-soft"}`} style={delay(1.1)}>
            {ageSentence(job.signals)}
          </li>
          {flags.map((flag, i) => (
            <li key={flag} className="hx-pop rounded-full bg-b-blush px-3 py-1.5 text-b-red" style={delay(1.4 + i * 0.3)}>
              {FLAG_TEXT[flag]!.short}
            </li>
          ))}
        </ul>

        {quote ? (
          <blockquote className="hx-rise mt-4 rounded-2xl bg-b-paper px-4 py-3.5 font-friendly text-[0.95rem] leading-relaxed font-medium text-b-ink" style={delay(2)}>
            “{quote}”
          </blockquote>
        ) : (
          typical !== null && (
            <p className="hx-rise mt-4 rounded-2xl bg-b-paper px-4 py-3.5 font-friendly text-[0.95rem] text-b-ink" style={delay(2)}>
              {job.company} usually fills roles in {pluralize(typical, "day")}.
            </p>
          )
        )}

        <Link
          href={`/jobs/${job.id}`}
          className="hx-rise mt-4 flex items-center justify-between gap-3 rounded-2xl bg-b-mint px-4 py-3 font-friendly text-sm font-bold text-b-green hover:underline"
          style={delay(3.4)}
        >
          See this posting&apos;s full record
          <span aria-hidden="true">→</span>
        </Link>
      </article>

      <Note
        className="top-14 left-0 -rotate-3 lg:left-4"
        at={1.2}
        arrow="M4 12 Q 52 8 90 44 M 78 42 L 90 44 L 88 32"
        arrowClass="top-24 left-[10.5rem] lg:left-[12rem]"
      >
        {job.signals.age_known ? `first seen ${formatDate(job.first_seen)},` : "here before we\nstarted watching,"}
        <br />
        still up today
      </Note>
      {quote && (
        <Note
          className="top-[13.5rem] right-0 rotate-3 lg:right-2"
          at={2.3}
          arrow="M96 10 Q 50 6 12 34 M 22 36 L 12 34 L 16 24"
          arrowClass="top-[12rem] right-[9.5rem] lg:right-[10.5rem]"
        >
          they say it
          <br />
          themselves
        </Note>
      )}
      {fNote && (
        <Note
          className="-top-2 right-6 rotate-2 whitespace-pre-line"
          at={2.8}
          arrow="M80 6 Q 40 10 18 52 M 14 40 L 18 52 L 28 46"
          arrowClass="top-10 right-[13rem]"
        >
          {fNote}
        </Note>
      )}

      <GhostMascot className="hx-mascot absolute right-[4%] bottom-0 hidden w-36 md:block" />
      <span aria-hidden="true" className="absolute right-[6%] bottom-0 hidden h-3 w-28 rounded-full bg-b-ink/8 blur-[2px] md:block" />
    </div>
  );
}

function Reason({
  tint,
  label,
  title,
  body,
  children,
  delaySeconds,
}: {
  tint: string;
  label: string;
  title: string;
  body: string;
  children: ReactNode;
  delaySeconds: number;
}) {
  return (
    <Reveal delay={delaySeconds} className="h-full">
      <div className={`flex h-full flex-col rounded-[1.75rem] p-7 ${tint}`}>
        <p className="font-friendly text-xs font-bold tracking-[0.14em] text-b-soft uppercase">{label}</p>
        <h3 className="mt-2 text-[1.65rem] leading-tight font-bold tracking-[-0.02em] text-b-ink">{title}</h3>
        <p className="mt-2.5 font-friendly text-base text-b-soft">{body}</p>
        <div className="mt-auto pt-6">
          <div className="rounded-2xl bg-b-card px-5 py-4 shadow-brand">{children}</div>
        </div>
      </div>
    </Reveal>
  );
}

export default async function HomePage() {
  await connection();
  const [stats, highRisk] = await Promise.all([
    api.stats(),
    api.jobs({ risk: ["high"], role: ["sde", "data_eng", "data"], sort: "oldest", limit: 20 }),
  ]);
  const exhibit = pickExhibit(highRisk.items);
  const detail = exhibit ? await api.job(exhibit.id).catch(() => null) : null;
  const updated = stats.last_run ? ago(stats.last_run.finished_at ?? stats.last_run.started_at) : null;
  const openRoles = stats.tech_active_jobs.toLocaleString("en-CA");
  const flagged = stats.tech_high_risk_active_jobs.toLocaleString("en-CA");
  const tickerItems = [
    `${openRoles} open tech roles`,
    `${flagged} flagged high ghost risk`,
    `${stats.tech_new_last_7_days.toLocaleString("en-CA")} first seen this week`,
    `${pluralize(stats.companies, "employer")} tracked`,
    ...(updated ? [`Updated ${updated}`] : []),
  ];

  return (
    <div className="home-b overflow-x-clip bg-b-paper font-friendly text-b-ink">
      <section className="px-4 sm:px-6 lg:px-10">
        <div className="mx-auto flex max-w-4xl flex-col items-center pt-12 text-center sm:pt-20">
          <p className="inline-flex items-center gap-2 rounded-full border border-b-line bg-b-card px-3.5 py-1.5 text-sm font-semibold text-b-ink">
            <MiniGhost className="size-4 text-b-ink" />
            {flagged} postings flagged high ghost risk right now
          </p>
          <h1 className="mt-6 text-[3.1rem] leading-[1.02] font-extrabold tracking-[-0.045em] sm:text-[5.25rem]">
            Apply where they&apos;re{" "}
            <span className="relative inline-block -rotate-[1.5deg] rounded-[1.1rem] bg-b-yellow px-3 text-b-on-yellow sm:px-4">actually</span> hiring.
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-b-soft sm:text-xl sm:leading-[1.9rem]">
            Every tech job in Canada, with the record job boards don&apos;t keep: when it really opened, whether it was quietly reposted, and
            whether it&apos;s a real opening at all.
          </p>
          <HomeSearch />
          <ul className="mt-5 flex flex-wrap items-center justify-center gap-2" aria-label="Popular searches">
            {QUICK_LINKS.map(({ label, href, tint, dot }) => (
              <li key={label}>
                <Link
                  href={href}
                  className={`inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-sm font-semibold text-b-ink transition-transform hover:-translate-y-0.5 ${tint}`}
                >
                  <span aria-hidden="true" className={`size-2 rounded-full ${dot}`} />
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <section aria-label="A real posting from today's data">
          {exhibit ? (
            <Exhibit job={exhibit} detail={detail} />
          ) : (
            <div className="mx-auto my-16 flex max-w-md flex-col items-center gap-3 text-center">
              <GhostMascot className="w-24" />
              <p className="font-semibold">No high-risk postings right now.</p>
              <p className="text-sm text-b-soft">Ghost signals build up as Ghostless watches postings over time.</p>
            </div>
          )}
        </section>
      </section>

      <section aria-label="Today's numbers" className="ticker overflow-hidden bg-b-yellow py-4 text-b-on-yellow">
        <ul className="sr-only">
          {tickerItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div aria-hidden="true" className="ticker-track flex w-max">
          {[0, 1].map((copy) => (
            <div key={copy} className="flex shrink-0 items-center">
              {[...tickerItems, ...tickerItems].map((item, i) => (
                <span key={`${copy}-${i}`} className="flex items-center gap-7 pr-7 font-brand text-xl font-bold tracking-[-0.02em] whitespace-nowrap">
                  {item}
                  <MiniGhost className="size-5" />
                </span>
              ))}
            </div>
          ))}
        </div>
      </section>

      <section aria-labelledby="why" className="px-4 pt-24 pb-8 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-280">
          <Reveal>
            <h2 id="why" className="text-center text-4xl font-extrabold tracking-[-0.04em] sm:text-[3.25rem]">
              What job boards don&apos;t tell you.
            </h2>
          </Reveal>
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            <Reason tint="bg-b-blush" label="True age" title="The day it really opened." body="Ghostless records the day it first sees a posting. A repost can't reset it." delaySeconds={0}>
              <p className="font-hand text-[1.75rem] leading-tight">{exhibit ? ageSentence(exhibit.signals).toLowerCase() : "open 41 days"}</p>
              <p className="text-xs font-semibold text-b-faint">{exhibit ? `${exhibit.company}, from today's data` : "Example"}</p>
            </Reason>
            <Reason
              tint="bg-b-lilac"
              label="Ghost signals"
              title="Evidence, not a verdict."
              body="Reposts, duplicates, roles left up for months, and postings that say they aren't a real vacancy, quoted."
              delaySeconds={0.12}
            >
              <div className="flex flex-wrap gap-2">
                <RiskBadge risk="high" />
                <RiskBadge risk="medium" />
              </div>
              <p className="mt-2 text-xs font-semibold text-b-faint">Each flag links to the words that triggered it</p>
            </Reason>
            <Reason
              tint="bg-b-mint"
              label="Resume match"
              title="A score that explains itself."
              body="Every requirement marked as met or missing, with what to change before you apply."
              delaySeconds={0.24}
            >
              <div className="flex items-center gap-3">
                <Ring score={82} size="sm" />
                <div className="text-sm">
                  <p className="flex flex-wrap items-center gap-x-1.5 font-semibold">
                    <CheckIcon className="size-4 text-b-green" /> Python
                    <CheckIcon className="ml-1 size-4 text-b-green" /> SQL
                    <CrossIcon className="ml-1 size-4 text-b-faint" /> Kafka
                  </p>
                  <p className="text-xs font-semibold text-b-faint">Example</p>
                </div>
              </div>
            </Reason>
          </div>
          <p className="mt-8 text-center">
            <Link href="/how-it-works" className="text-base font-semibold text-accent hover:underline">
              How the signals are calculated →
            </Link>
          </p>
        </div>
      </section>

      <section className="px-4 py-24 sm:px-6 sm:py-28 lg:px-10">
        <Reveal className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <GhostMascot className="w-20" />
          <h2 className="mt-5 text-4xl font-extrabold tracking-[-0.04em] sm:text-[3.25rem] sm:leading-[1.05]">
            Spend your time on roles that are{" "}
            <span className="inline-block -rotate-1 rounded-[0.9rem] bg-b-yellow px-2.5 text-b-on-yellow">really open.</span>
          </h2>
          <Link href={jobsHref(EMPTY_FILTERS)} className="btn btn-primary btn-lg mt-9">
            Search {openRoles} open tech roles
          </Link>
          <p className="mt-4 text-sm text-b-faint">
            Free. {percent(stats.tech_high_risk_active_jobs, stats.tech_active_jobs)} of today&apos;s open tech roles carry high ghost risk.
          </p>
        </Reveal>
      </section>
    </div>
  );
}

