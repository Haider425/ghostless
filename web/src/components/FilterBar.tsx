import Link from "next/link";
import type { ReactNode } from "react";

import { EMPTY_FILTERS, type JobFilters, FRESHNESS, LEVELS, LOCATIONS, RISKS, activeFilterCount, jobsHref } from "@/lib/filters";
import { LEVEL_LABELS, RISK_LABELS } from "@/lib/format";

import { AutoSubmit } from "./AutoSubmit";
import { ChevronDownIcon, FilterIcon, SearchIcon } from "./Icons";

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

export const SORT_LABELS = { newest: "Newest", oldest: "Oldest", salary: "Highest pay", company: "Company A to Z" };

/**
 * One filter as a dropdown pill. Built on <details>, so it opens and the form
 * submits without JavaScript; AutoSubmit adds instant updates and closes
 * dropdowns on outside clicks. On phones the panel becomes a bottom sheet.
 */
function Dropdown({
  label,
  summary,
  active,
  icon,
  children,
}: {
  label: string;
  summary?: string;
  active: boolean;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <details data-popover className="group relative">
      <summary className="pill" data-active={active || undefined}>
        {icon}
        <span>
          {summary ? `${label}: ` : label}
          {summary && <span className="font-semibold">{summary}</span>}
        </span>
        <ChevronDownIcon className="size-3.5 opacity-70 transition-transform group-open:rotate-180" />
      </summary>
      <div className="fixed inset-x-3 bottom-3 z-40 max-h-[75dvh] overflow-y-auto rounded-2xl border border-line bg-surface p-4 shadow-pop sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:mt-2 sm:w-72 sm:p-2">
        {children}
        <button type="submit" className="btn btn-primary mt-3 w-full">
          Show results
        </button>
      </div>
    </details>
  );
}

function Group({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-0.5 [&+&]:mt-2 [&+&]:border-t [&+&]:border-line [&+&]:pt-2">
      <legend className="mb-1 px-2.5 pt-1.5 text-meta font-semibold text-ink-faint">{legend}</legend>
      {children}
    </fieldset>
  );
}

function Option({ type, name, value, checked, children }: { type: "checkbox" | "radio"; name: string; value: string; checked: boolean; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2.5 text-ui text-ink hover:bg-sunken sm:py-2">
      {/* keyed by state: when the URL changes (Clear all, back button) the box resets to match it */}
      <input key={`${value}-${checked}`} type={type} name={name} value={value} defaultChecked={checked} className="size-4 shrink-0" />
      {children}
    </label>
  );
}

function summarize<T extends string>(chosen: T[], labels: Record<T, string>): string | undefined {
  if (chosen.length === 0) return undefined;
  return chosen.length === 1 ? labels[chosen[0]!] : `${chosen.length} selected`;
}

/**
 * The jobs toolbar: a search box, the three filters people use most (level,
 * location, season), the rest under "More filters" (ghost risk, first seen,
 * pay), and the sort order on the right.
 */
export function FilterBar({ filters, seasons = [] }: { filters: JobFilters; seasons?: { term: string; jobs: number }[] }) {
  const count = activeFilterCount(filters);
  const more = [filters.risk.length > 0, filters.newWithinDays !== null, filters.hasSalary].filter(Boolean).length;
  return (
    <form id={FILTER_FORM_ID} action="/jobs" method="get" role="search" className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center lg:gap-2.5">
      <div className="relative min-w-0 lg:w-[26rem] xl:w-[29rem]">
        <label htmlFor="jobs-q" className="sr-only">
          Search jobs
        </label>
        <SearchIcon className="pointer-events-none absolute top-1/2 left-4 size-[18px] -translate-y-1/2 text-ink-faint" />
        <input
          id="jobs-q"
          key={filters.q}
          type="search"
          name="q"
          defaultValue={filters.q}
          maxLength={100}
          placeholder="Title, company, skill or city"
          autoComplete="off"
          className="field field-soft field-lg pl-11"
        />
      </div>

      {/* phones: one scrolling row (dropdowns open as bottom sheets, so nothing is clipped) */}
      <div className="scroll-quiet -mx-4 flex flex-1 items-center gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0 [&>*]:shrink-0">
        <Dropdown label="Level" summary={summarize(filters.level, LEVEL_LABELS)} active={filters.level.length > 0}>
          <Group legend="Level">
            {LEVELS.map((level) => (
              <Option key={level} type="checkbox" name="level" value={level} checked={filters.level.includes(level)}>
                {LEVEL_LABELS[level]}
              </Option>
            ))}
          </Group>
        </Dropdown>
        <Dropdown
          label="Location"
          summary={filters.location === "any" ? undefined : LOCATION_LABELS[filters.location]}
          active={filters.location !== "any"}
        >
          <Group legend="Location">
            {LOCATIONS.map((location) => (
              <Option key={location} type="radio" name="location" value={location} checked={filters.location === location}>
                {LOCATION_LABELS[location]}
              </Option>
            ))}
          </Group>
        </Dropdown>
        {seasons.length > 0 && (
          <Dropdown label="Season" summary={filters.term.length === 1 ? filters.term[0] : filters.term.length ? `${filters.term.length} selected` : undefined} active={filters.term.length > 0}>
            <Group legend="Season">
              {seasons.map(({ term, jobs }) => (
                <Option key={term} type="checkbox" name="term" value={term} checked={filters.term.includes(term)}>
                  {term} <span className="text-ink-faint">({jobs.toLocaleString("en-CA")})</span>
                </Option>
              ))}
            </Group>
          </Dropdown>
        )}
        <Dropdown label="More filters" summary={more ? String(more) : undefined} active={more > 0} icon={<FilterIcon className="size-4" />}>
          <Group legend="Ghost risk">
            {RISKS.map((risk) => (
              <Option key={risk} type="checkbox" name="risk" value={risk} checked={filters.risk.includes(risk)}>
                {RISK_LABELS[risk]}
              </Option>
            ))}
          </Group>
          <Group legend="First seen">
            <Option type="radio" name="new" value="" checked={filters.newWithinDays === null}>
              Any time
            </Option>
            {FRESHNESS.map((days) => (
              <Option key={days} type="radio" name="new" value={String(days)} checked={filters.newWithinDays === days}>
                {FRESHNESS_LABELS[days]}
              </Option>
            ))}
          </Group>
          <Group legend="Pay">
            <Option type="checkbox" name="salary" value="1" checked={filters.hasSalary}>
              Shows pay
            </Option>
          </Group>
        </Dropdown>

        {/* Keep the role tab, company and skill filters when other filters change */}
        {filters.role !== "tech" && <input type="hidden" name="role" value={filters.role} />}
        {filters.company.map((c) => (
          <input key={`c-${c}`} type="hidden" name="company" value={c} />
        ))}
        {filters.skill.map((s) => (
          <input key={`s-${s}`} type="hidden" name="skill" value={s} />
        ))}

        {count > 0 && (
          <Link href={jobsHref({ ...EMPTY_FILTERS, q: filters.q, role: filters.role })} className="link px-2 text-ui">
            Clear all
          </Link>
        )}
      </div>

      <label className="flex items-center gap-1 text-ui text-ink-soft lg:ml-auto">
        Sort:
        <select
          key={filters.sort}
          name="sort"
          defaultValue={filters.sort}
          className="cursor-pointer rounded-lg bg-transparent py-1.5 pr-1 font-medium text-ink hover:bg-sunken focus-visible:outline-2"
        >
          {Object.entries(SORT_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <AutoSubmit formId={FILTER_FORM_ID} />
    </form>
  );
}
