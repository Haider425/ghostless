import Link from "next/link";
import type { ReactNode } from "react";

import { EMPTY_FILTERS, type JobFilters, FRESHNESS, LEVELS, LOCATIONS, RISKS, activeFilterCount, jobsHref } from "@/lib/filters";
import { LEVEL_LABELS, RISK_LABELS } from "@/lib/format";

import { AutoSubmit } from "./AutoSubmit";
import { ChevronDownIcon, SearchIcon } from "./Icons";

export const FILTER_FORM_ID = "job-filters";

const LOCATION_LABELS: Record<(typeof LOCATIONS)[number], string> = {
  any: "Anywhere",
  canada: "In Canada",
  remote: "Remote",
  canada_or_remote: "Canada or remote",
};

const FRESHNESS_LABELS: Record<number, string> = {
  1: "Last 24 hours",
  3: "Last 3 days",
  7: "Last week",
  14: "Last 2 weeks",
  30: "Last month",
};

/**
 * One filter as a dropdown. Built on <details>, so it opens and the form
 * submits without JavaScript; AutoSubmit adds instant updates and closes
 * dropdowns on outside clicks. On phones the panel becomes a bottom sheet.
 */
function Dropdown({ label, summary, active, children }: { label: string; summary?: string; active: boolean; children: ReactNode }) {
  return (
    <details data-popover className="group relative">
      <summary
        className={`btn btn-secondary btn-sm gap-1.5 group-open:bg-sunken ${active ? "border-accent/60 bg-accent-tint text-accent hover:bg-accent-tint" : ""}`}
      >
        <span>
          {summary ? `${label}: ` : label}
          {summary && <span className="font-normal">{summary}</span>}
        </span>
        <ChevronDownIcon className="size-3.5 opacity-70 transition-transform group-open:rotate-180" />
      </summary>
      <div className="fixed inset-x-3 bottom-3 z-40 panel p-4 shadow-pop sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:mt-1.5 sm:w-60 sm:rounded-xl sm:p-2">
        <fieldset className="space-y-0.5">
          <legend className="mb-1 px-2 pt-1 text-xs font-medium text-ink-faint">{label}</legend>
          {children}
        </fieldset>
        <button
          type="submit"
          className="btn btn-primary btn-sm mt-3 w-full"
        >
          Show results
        </button>
      </div>
    </details>
  );
}

function Option({ type, name, value, checked, children }: { type: "checkbox" | "radio"; name: string; value: string; checked: boolean; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-sm text-ink hover:bg-sunken sm:py-1.5">
      {/* keyed by state: when the URL changes (Clear all, back button) the box resets to match it */}
      <input
        key={`${value}-${checked}`}
        type={type}
        name={name}
        value={value}
        defaultChecked={checked}
        className="size-4 shrink-0 accent-[var(--accent)]"
      />
      {children}
    </label>
  );
}

function summarize<T extends string>(chosen: T[], labels: Record<T, string>): string | undefined {
  if (chosen.length === 0) return undefined;
  return chosen.length === 1 ? labels[chosen[0]!] : `${chosen.length} selected`;
}

export function FilterBar({ filters, seasons = [] }: { filters: JobFilters; seasons?: { term: string; jobs: number }[] }) {
  const count = activeFilterCount(filters);
  return (
    <form id={FILTER_FORM_ID} action="/jobs" method="get" role="search" className="space-y-3">
      <div className="flex gap-2">
        <label htmlFor="jobs-q" className="sr-only">
          Search jobs
        </label>
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-faint" />
          <input
            id="jobs-q"
            key={filters.q}
            type="search"
            name="q"
            defaultValue={filters.q}
            maxLength={100}
            placeholder="Title, company, skill or city: amazon, python, toronto..."
            autoComplete="off"
            className="field h-10 pl-10"
          />
        </div>
        <button type="submit" className="btn btn-primary h-10 px-4">
          Search
        </button>
      </div>

      {/* phones: one scrolling row (dropdowns open as bottom sheets, so nothing is clipped) */}
      <div className="scroll-quiet flex items-center gap-1.5 max-sm:overflow-x-auto max-sm:pb-1 sm:flex-wrap [&>*]:shrink-0">
        <Dropdown label="Level" summary={summarize(filters.level, LEVEL_LABELS)} active={filters.level.length > 0}>
          {LEVELS.map((level) => (
            <Option key={level} type="checkbox" name="level" value={level} checked={filters.level.includes(level)}>
              {LEVEL_LABELS[level]}
            </Option>
          ))}
        </Dropdown>
        {seasons.length > 0 && (
          <Dropdown label="Season" summary={filters.term.length ? filters.term.join(", ") : undefined} active={filters.term.length > 0}>
            {seasons.map(({ term, jobs }) => (
              <Option key={term} type="checkbox" name="term" value={term} checked={filters.term.includes(term)}>
                {term} <span className="text-ink-faint">({jobs.toLocaleString("en-CA")})</span>
              </Option>
            ))}
          </Dropdown>
        )}
        <Dropdown
          label="Location"
          summary={filters.location === "any" ? undefined : LOCATION_LABELS[filters.location]}
          active={filters.location !== "any"}
        >
          {LOCATIONS.map((location) => (
            <Option key={location} type="radio" name="location" value={location} checked={filters.location === location}>
              {LOCATION_LABELS[location]}
            </Option>
          ))}
        </Dropdown>
        <Dropdown
          label="First seen"
          summary={filters.newWithinDays ? FRESHNESS_LABELS[filters.newWithinDays] : undefined}
          active={filters.newWithinDays !== null}
        >
          <Option type="radio" name="new" value="" checked={filters.newWithinDays === null}>
            Any time
          </Option>
          {FRESHNESS.map((days) => (
            <Option key={days} type="radio" name="new" value={String(days)} checked={filters.newWithinDays === days}>
              {FRESHNESS_LABELS[days]}
            </Option>
          ))}
        </Dropdown>
        <Dropdown label="Ghost risk" summary={summarize(filters.risk, { low: "No flags", medium: "Some flags", high: "High" })} active={filters.risk.length > 0}>
          {RISKS.map((risk) => (
            <Option key={risk} type="checkbox" name="risk" value={risk} checked={filters.risk.includes(risk)}>
              {RISK_LABELS[risk]}
            </Option>
          ))}
        </Dropdown>
        <label
          className="btn btn-secondary btn-sm cursor-pointer has-[:checked]:border-accent/60 has-[:checked]:bg-accent-tint has-[:checked]:text-accent has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--focus)]"
        >
          <input
            key={String(filters.hasSalary)}
            type="checkbox"
            name="salary"
            value="1"
            defaultChecked={filters.hasSalary}
            className="size-4 accent-[var(--accent)]"
          />
          Shows pay
        </label>

        {/* Keep the role tab, sort, company and skill filters when other filters change */}
        {filters.role !== "tech" && <input type="hidden" name="role" value={filters.role} />}
        {filters.sort !== "newest" && <input type="hidden" name="sort" value={filters.sort} />}
        {filters.company.map((c) => (
          <input key={`c-${c}`} type="hidden" name="company" value={c} />
        ))}
        {filters.skill.map((s) => (
          <input key={`s-${s}`} type="hidden" name="skill" value={s} />
        ))}

        {count > 0 && (
          <Link
            href={jobsHref({ ...EMPTY_FILTERS, q: filters.q, role: filters.role })}
            className="link ml-1 text-sm"
          >
            Clear all
          </Link>
        )}
      </div>
      <AutoSubmit formId={FILTER_FORM_ID} />
    </form>
  );
}
