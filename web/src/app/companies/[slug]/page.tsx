import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { CompanyLogo } from "@/components/CompanyLogo";
import { ChevronRightIcon } from "@/components/Icons";
import { JobList } from "@/components/JobCard";
import { Stat } from "@/components/Stat";
import { WeeklyChart } from "@/components/WeeklyChart";
import { api } from "@/lib/api";
import { EMPTY_FILTERS, TECH_ROLES, jobsHref } from "@/lib/filters";
import { LEVEL_LABELS, ROLE_LABELS, formatDate, percent, pluralize } from "@/lib/format";

type Props = { params: Promise<{ slug: string }> };

const getCompany = cache((slug: string) => api.company(slug));

async function load(params: Props["params"]) {
  const { slug } = await params;
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) notFound();
  const company = await getCompany(slug);
  if (!company) notFound();
  return company;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const company = await load(params);
  return {
    title: `${company.name} jobs and hiring record`,
    description: `${company.name}: ${company.tech_active_jobs} open tech roles, how fast they fill, and how many show ghost job signals.`,
    alternates: { canonical: `/companies/${company.slug}` },
  };
}

/** A labelled horizontal bar; the number is always printed, so the bar is only a guide. */
function BarRow({ label, value, max, href }: { label: string; value: number; max: number; href?: string }) {
  const name = href ? (
    <Link href={href} className="hover:text-accent hover:underline">
      {label}
    </Link>
  ) : (
    label
  );
  return (
    <li className="grid grid-cols-[minmax(0,9rem)_1fr_2.5rem] items-center gap-3 text-sm">
      <span className="truncate text-ink">{name}</span>
      <span className="h-2 rounded-full bg-sunken" aria-hidden="true">
        <span className="block h-2 rounded-full bg-bar-new" style={{ width: `${Math.max(3, (value / Math.max(1, max)) * 100)}%` }} />
      </span>
      <span className="text-right font-medium text-ink">{value}</span>
    </li>
  );
}

export default async function CompanyPage({ params }: Props) {
  const company = await load(params);
  const companyFilters = { ...EMPTY_FILTERS, company: [company.name] };
  const latest = await api.jobs({ company: [company.name], role: [...TECH_ROLES], limit: 6 });
  const highShare = company.active_jobs ? company.high_risk_jobs / company.active_jobs : 0;
  const roleMax = Math.max(...company.roles.map((r) => r.count), 1);
  const levelMax = Math.max(...company.levels.map((l) => l.count), 1);
  const skillMax = Math.max(...company.top_skills.map((s) => s.postings), 1);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <nav aria-label="Breadcrumb" className="mb-6">
        <ol className="flex items-center gap-1 text-sm text-ink-soft">
          <li>
            <Link href="/companies" className="hover:text-accent hover:underline">
              Companies
            </Link>
          </li>
          <li aria-hidden="true">
            <ChevronRightIcon className="size-3.5 text-ink-faint" />
          </li>
          <li aria-current="page" className="text-ink">
            {company.name}
          </li>
        </ol>
      </nav>

      <header className="mb-8 flex flex-wrap items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <CompanyLogo name={company.name} domain={company.domain} size="lg" />
          <div>
            <h1 className="text-4xl font-semibold text-ink">{company.name}</h1>
            <p className="text-ink-soft">Tracked daily since {formatDate(company.tracking_since)}</p>
          </div>
        </div>
        <Link
          href={jobsHref(companyFilters)}
          className="inline-flex h-11 items-center rounded-lg bg-accent px-5 font-medium text-on-accent hover:bg-accent-hover"
        >
          See all {pluralize(company.tech_active_jobs, "open tech role")}
        </Link>
      </header>

      <dl className="mb-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Open tech roles" value={company.tech_active_jobs.toLocaleString("en-CA")} note={`${pluralize(company.active_jobs, "posting")} in all`} />
        <Stat label="New this week" value={company.new_last_7_days.toLocaleString("en-CA")} note={`${company.closed_last_30_days} closed in the last 30 days`} />
        <Stat
          label="Usually fills roles in"
          value={company.typical_days_open ? pluralize(company.typical_days_open, "day") : "No data yet"}
          note={company.typical_days_open ? "median, from first seen to taken down" : "needs 5 closed postings"}
        />
        <Stat
          label="High ghost risk"
          value={percent(company.high_risk_jobs, company.active_jobs)}
          note={`${pluralize(company.high_risk_jobs, "open posting")}`}
          tone={highShare >= 0.2 ? "warn" : undefined}
        />
      </dl>

      <div className="mb-10 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
          <h2 className="sr-only">Hiring activity</h2>
          <WeeklyChart weeks={company.weekly} title="Tech postings, last 12 weeks" />
        </section>
        <div className="grid gap-5">
          <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <h2 className="mb-4 font-sans text-base font-semibold text-ink">Open postings by role</h2>
            <ul className="space-y-2.5">
              {company.roles.map((r) => (
                <BarRow
                  key={r.key}
                  label={ROLE_LABELS[r.key as keyof typeof ROLE_LABELS] ?? r.key}
                  value={r.count}
                  max={roleMax}
                  href={jobsHref(companyFilters, { role: r.key === "other" ? "all" : (r.key as (typeof TECH_ROLES)[number]) })}
                />
              ))}
            </ul>
          </section>
          <section className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <h2 className="mb-4 font-sans text-base font-semibold text-ink">Open tech roles by level</h2>
            <ul className="space-y-2.5">
              {company.levels.map((l) => (
                <BarRow
                  key={l.key}
                  label={LEVEL_LABELS[l.key as keyof typeof LEVEL_LABELS] ?? l.key}
                  value={l.count}
                  max={levelMax}
                  href={jobsHref(companyFilters, { level: [l.key as keyof typeof LEVEL_LABELS] })}
                />
              ))}
            </ul>
          </section>
        </div>
      </div>

      <div className="grid gap-10 lg:grid-cols-[1fr_20rem]">
        <section>
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-2xl font-semibold text-ink">Latest tech roles</h2>
            <Link href={jobsHref(companyFilters)} className="text-sm font-medium text-accent hover:underline">
              See all {company.tech_active_jobs.toLocaleString("en-CA")}
            </Link>
          </div>
          {latest.items.length ? (
            <JobList jobs={latest.items} headingLevel="h3" />
          ) : (
            <p className="rounded-xl border border-dashed border-line-strong p-6 text-sm text-ink-soft">
              {company.name} has no open tech roles right now.
            </p>
          )}
        </section>
        {company.top_skills.length > 0 && (
          <section>
            <h2 className="mb-1 font-sans text-base font-semibold text-ink">Skills {company.name} asks for</h2>
            <p className="mb-4 text-sm text-ink-soft">Open tech postings mentioning each skill.</p>
            <ul className="space-y-2.5">
              {company.top_skills.map((s) => (
                <BarRow
                  key={s.skill}
                  label={s.skill}
                  value={s.postings}
                  max={skillMax}
                  href={jobsHref(companyFilters, { skill: [s.skill] })}
                />
              ))}
            </ul>
            <p className="mt-5 text-sm text-ink-soft">
              <Link href="/skills" className="font-medium text-accent hover:underline">
                Compare your skills
              </Link>{" "}
              with what employers ask for most.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
