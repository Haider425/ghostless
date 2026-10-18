import type { GhostRisk, JobQuery, Level, RoleType } from "./api-types";

/*
  Job search filters live in the URL, so every search is shareable, bookmarkable
  and works without JavaScript. Unknown or malformed values are dropped rather
  than passed to the API, so a hand-edited URL never produces an error page.
*/

export type SearchParams = Record<string, string | string[] | undefined>;

export const LEVELS = ["intern", "new_grad", "mid", "senior"] as const satisfies readonly Level[];
export const TECH_ROLES = ["sde", "data_eng", "data", "ml", "hardware", "security"] as const satisfies readonly RoleType[];
/**
 * The role tab: one tech role, "tech" (every tech role, the default) or
 * "all" (every posting, including non-tech roles at tech employers).
 */
export const ROLE_SCOPES = ["tech", ...TECH_ROLES, "all"] as const;
export type RoleScope = (typeof ROLE_SCOPES)[number];
export const RISKS = ["low", "medium", "high"] as const satisfies readonly GhostRisk[];
export const LOCATIONS = ["any", "canada", "remote", "canada_or_remote"] as const;
export const SORTS = ["newest", "oldest", "salary", "company"] as const;
export const FRESHNESS = [1, 3, 7, 14, 30] as const;
export const PAGE_SIZE = 25;
const MAX_PAGE = 400; // the API caps offset at 10,000

export type Location = (typeof LOCATIONS)[number];
export type Sort = (typeof SORTS)[number];

export interface JobFilters {
  q: string;
  level: Level[];
  role: RoleScope;
  risk: GhostRisk[];
  company: string[];
  skill: string[];
  /** seasons, like "Summer 2027" */
  term: string[];
  location: Location;
  newWithinDays: number | null;
  hasSalary: boolean;
  sort: Sort;
  page: number;
  /** the posting open in the preview pane (desktop) */
  selected: number | null;
}

function all(params: SearchParams, key: string): string[] {
  const value = params[key];
  if (value === undefined) return [];
  return (Array.isArray(value) ? value : [value]).map((v) => v.trim()).filter(Boolean);
}

function one(params: SearchParams, key: string): string | undefined {
  return all(params, key)[0];
}

function pick<T extends string>(values: string[], allowed: readonly T[]): T[] {
  return [...new Set(values.filter((v): v is T => (allowed as readonly string[]).includes(v)))];
}

export function parseFilters(params: SearchParams): JobFilters {
  const location = one(params, "location");
  const sort = one(params, "sort");
  const days = Number(one(params, "new"));
  const page = Math.trunc(Number(one(params, "page")));
  const selected = Number(one(params, "job"));
  return {
    q: (one(params, "q") ?? "").slice(0, 100),
    level: pick(all(params, "level"), LEVELS),
    role: (ROLE_SCOPES as readonly string[]).includes(one(params, "role") ?? "") ? (one(params, "role") as RoleScope) : "tech",
    risk: pick(all(params, "risk"), RISKS),
    company: all(params, "company").slice(0, 20),
    skill: all(params, "skill").slice(0, 20),
    term: all(params, "term").filter((t) => /^(Summer|Fall|Winter|Spring) \d{4}$/.test(t)).slice(0, 8),
    location: (LOCATIONS as readonly string[]).includes(location ?? "") ? (location as Location) : "any",
    newWithinDays: (FRESHNESS as readonly number[]).includes(days) ? days : null,
    hasSalary: one(params, "salary") === "1",
    sort: (SORTS as readonly string[]).includes(sort ?? "") ? (sort as Sort) : "newest",
    page: Number.isFinite(page) && page >= 1 ? Math.min(page, MAX_PAGE) : 1,
    selected: Number.isSafeInteger(selected) && selected > 0 ? selected : null,
  };
}

export function toApiQuery(filters: JobFilters): JobQuery {
  return {
    q: filters.q || undefined,
    level: filters.level.length ? filters.level : undefined,
    role: filters.role === "all" ? undefined : filters.role === "tech" ? [...TECH_ROLES] : [filters.role],
    risk: filters.risk.length ? filters.risk : undefined,
    company: filters.company.length ? filters.company : undefined,
    skill: filters.skill.length ? filters.skill : undefined,
    term: filters.term.length ? filters.term : undefined,
    location: filters.location,
    new_within_days: filters.newWithinDays ?? undefined,
    has_salary: filters.hasSalary || undefined,
    sort: filters.sort,
    limit: PAGE_SIZE,
    offset: (filters.page - 1) * PAGE_SIZE,
  };
}

/**
 * The URL for a job search, with optional changes applied. Defaults are left
 * out to keep URLs short. Changing anything but the selection clears the
 * selection, since the selected posting may not be in the new results.
 */
export function jobsHref(filters: JobFilters, changes: Partial<JobFilters> = {}): string {
  const keepsSelection = Object.keys(changes).every((key) => key === "selected");
  const next = { ...filters, ...(keepsSelection ? {} : { selected: null }), ...changes };
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  next.level.forEach((v) => params.append("level", v));
  if (next.role !== "tech") params.set("role", next.role);
  next.risk.forEach((v) => params.append("risk", v));
  next.company.forEach((v) => params.append("company", v));
  next.skill.forEach((v) => params.append("skill", v));
  next.term.forEach((v) => params.append("term", v));
  if (next.location !== "any") params.set("location", next.location);
  if (next.newWithinDays) params.set("new", String(next.newWithinDays));
  if (next.hasSalary) params.set("salary", "1");
  if (next.sort !== "newest") params.set("sort", next.sort);
  if (next.page > 1) params.set("page", String(next.page));
  if (next.selected) params.set("job", String(next.selected));
  const query = params.toString();
  return query ? `/jobs?${query}` : "/jobs";
}

export const EMPTY_FILTERS: JobFilters = parseFilters({});

export function activeFilterCount(filters: JobFilters): number {
  return (
    filters.level.length +
    filters.risk.length +
    filters.company.length +
    filters.skill.length +
    filters.term.length +
    (filters.location !== "any" ? 1 : 0) +
    (filters.newWithinDays ? 1 : 0) +
    (filters.hasSalary ? 1 : 0)
  );
}
