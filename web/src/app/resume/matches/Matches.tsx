"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { ChevronDownIcon, DocIcon } from "@/components/Icons";
import { JobCard } from "@/components/JobCard";
import { StaticMatches } from "@/components/Match";
import { useSite } from "@/components/SiteContext";
import type { Level, RoleType } from "@/lib/api";
import type { Match, Recommendation, RecommendationPage } from "@/lib/api-types";
import { LEVELS, TECH_ROLES } from "@/lib/filters";
import { LEVEL_LABELS, ROLE_TABS } from "@/lib/format";
import { type ActiveResume, resumeQuery, useActiveResume } from "@/lib/resume";

const LOCATIONS = [
  { value: "any", label: "Anywhere" },
  { value: "canada", label: "In Canada" },
  { value: "remote", label: "Remote" },
  { value: "canada_or_remote", label: "Canada or remote" },
] as const;
type Loc = (typeof LOCATIONS)[number]["value"];

/* What the score is made of: the same weights as the scoring on the server (see How it works). */
const WEIGHTS = [
  ["Required skills", 35],
  ["Experience", 20],
  ["The posting's key terms", 15],
  ["Nice-to-haves", 10],
  ["Education", 10],
  ["Role and title", 10],
] as const;

/*
  The API ranks every open tech job for a location; level and role are
  narrowed here, over the ranked list, so the order stays the API's. When a
  filter leaves too few, more of the ranking loads, up to a few pages.
*/
const PAGE = 60;
const WANT = 20;
const MAX_AUTO_PAGES = 4;

async function load(resume: ActiveResume, location: Loc, includeRisky: boolean, offset: number, limit: number): Promise<RecommendationPage | null> {
  const response = await fetch("/api/resume/recommendations", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...resumeQuery(resume), location, include_high_risk: includeRisky, offset, limit }),
  }).catch(() => null);
  return response?.ok ? ((await response.json()) as RecommendationPage) : null;
}

/** A filter pill with a small menu, like the jobs page's. */
function Menu({ label, summary, active, children }: { label: string; summary?: string; active: boolean; children: ReactNode }) {
  return (
    <details data-popover className="group relative">
      <summary className="pill" data-active={active || undefined}>
        <span>
          {summary ? `${label}: ` : label}
          {summary && <span className="font-semibold">{summary}</span>}
        </span>
        <ChevronDownIcon className="size-3.5 opacity-70 transition-transform group-open:rotate-180" />
      </summary>
      <fieldset className="fixed inset-x-3 bottom-3 z-40 space-y-0.5 rounded-2xl border border-line bg-surface p-3 shadow-pop sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:mt-2 sm:w-64 sm:p-2">
        <legend className="sr-only">{label}</legend>
        {children}
      </fieldset>
    </details>
  );
}

function Choice({ type, checked, onChange, children }: { type: "checkbox" | "radio"; checked: boolean; onChange: () => void; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2.5 text-ui text-ink hover:bg-sunken sm:py-2">
      <input type={type} checked={checked} onChange={onChange} className="size-4 shrink-0" />
      {children}
    </label>
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

export function Matches() {
  const { resume, ready } = useActiveResume();
  const { prefs } = useSite();
  const [location, setLocation] = useState<Loc>(prefs.default_location);
  const [risky, setRisky] = useState(false);
  const [levels, setLevels] = useState<Level[]>([]);
  const [roles, setRoles] = useState<RoleType[]>([]);
  // Results remember what they were loaded for; anything else on screen is still loading.
  const [data, setData] = useState<{
    resume: ActiveResume;
    location: Loc;
    risky: boolean;
    items: Recommendation[];
    total: number;
    failed: boolean;
  } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (!resume) return;
    let live = true;
    void load(resume, location, risky, 0, PAGE).then((page) => {
      if (live) setData({ resume, location, risky, items: page?.items ?? [], total: page?.total ?? 0, failed: !page });
    });
    return () => {
      live = false;
    };
  }, [resume, location, risky]);

  const current = data && data.resume === resume && data.location === location && data.risky === risky ? data : null;
  const loaded = current?.items ?? [];
  const total = current?.total ?? 0;
  const items = loaded.filter(
    ({ job }) => (!levels.length || levels.includes(job.level)) && (!roles.length || roles.includes(job.role_type)),
  );
  const filtering = levels.length > 0 || roles.length > 0;
  const canLoadMore = loaded.length < total && loaded.length < 1000;
  const state: "loading" | "ready" | "more" | "error" = !current ? "loading" : current.failed ? "error" : loadingMore ? "more" : "ready";

  async function more() {
    if (!resume || !current) return;
    setLoadingMore(true);
    let next = current.items;
    // with a filter on, keep reading the ranking until there's a page's worth, a few pages at most
    for (let i = 0; i < (filtering ? MAX_AUTO_PAGES : 1); i++) {
      const page = await load(resume, location, risky, next.length, PAGE);
      if (!page) break;
      next = [...next, ...page.items];
      const shown = next.filter(
        ({ job }) => (!levels.length || levels.includes(job.level)) && (!roles.length || roles.includes(job.role_type)),
      ).length;
      if (!filtering || shown >= items.length + WANT || next.length >= current.total) break;
    }
    setData({ ...current, items: next });
    setLoadingMore(false);
  }

  if (!ready) return <div className="mt-8 h-64 animate-pulse rounded-2xl bg-sunken" aria-busy="true" />;
  if (!resume) {
    return (
      <div className="card mt-8 p-10 text-center">
        <p className="text-xl font-bold text-ink">Add your resume first</p>
        <p className="mx-auto mt-2 max-w-md text-ui text-ink-soft">Upload a PDF or Word file, or build one, and your matches appear here.</p>
        <div className="mt-6 flex justify-center gap-3">
          <Link href="/resume" className="btn btn-primary btn-lg">Upload resume</Link>
          <Link href="/resume/builder" className="btn btn-secondary btn-lg">Build one</Link>
        </div>
      </div>
    );
  }

  const scores: Record<number, Match> = Object.fromEntries(loaded.map((r) => [r.job.id, r.match]));

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-wrap items-center gap-2.5">
        <Link href="/resume" className="pill bg-sunken" title="Change which resume is matched">
          <DocIcon className="size-4 text-ink-soft" />
          <span>
            Matching with: <span className="font-semibold">{resume.title}</span>
          </span>
        </Link>
        <Menu label="Level" summary={levels.length === 1 ? LEVEL_LABELS[levels[0]!] : levels.length ? `${levels.length} selected` : undefined} active={levels.length > 0}>
          {LEVELS.map((level) => (
            <Choice key={level} type="checkbox" checked={levels.includes(level)} onChange={() => setLevels(toggle(levels, level))}>
              {LEVEL_LABELS[level]}
            </Choice>
          ))}
        </Menu>
        <Menu label="Location" summary={location === "any" ? undefined : LOCATIONS.find((l) => l.value === location)?.label} active={location !== "any"}>
          {LOCATIONS.map((l) => (
            <Choice key={l.value} type="radio" checked={location === l.value} onChange={() => setLocation(l.value)}>
              {l.label}
            </Choice>
          ))}
        </Menu>
        <Menu label="Role" summary={roles.length === 1 ? ROLE_TABS[roles[0]!] : roles.length ? `${roles.length} selected` : undefined} active={roles.length > 0}>
          {TECH_ROLES.map((role) => (
            <Choice key={role} type="checkbox" checked={roles.includes(role)} onChange={() => setRoles(toggle(roles, role))}>
              {ROLE_TABS[role]}
            </Choice>
          ))}
        </Menu>
        {filtering && (
          <button type="button" onClick={() => { setLevels([]); setRoles([]); }} className="link px-2 text-ui">
            Clear
          </button>
        )}
        <label className="flex cursor-pointer items-center gap-2.5 text-ui font-medium text-ink-soft sm:ml-auto">
          Include likely ghost jobs
          <input type="checkbox" role="switch" checked={risky} onChange={(e) => setRisky(e.target.checked)} className="peer sr-only" />
          <span
            aria-hidden="true"
            className="relative h-6 w-10 rounded-full bg-line-strong transition-colors peer-checked:bg-accent-solid peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus after:absolute after:top-0.75 after:left-0.75 after:size-4.5 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-4"
          />
        </label>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-labelledby="matches-heading" className="min-w-0">
          {state === "error" && <p role="alert" className="notice notice-danger mb-4">Matches couldn&apos;t load. Try again in a moment.</p>}
          {state === "loading" ? (
            <div className="panel space-y-1 p-2" aria-busy="true">
              {Array.from({ length: 5 }, (_, i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-sunken" />)}
            </div>
          ) : (
            <StaticMatches scores={scores}>
              <h2 id="matches-heading" className="mb-3 px-1 text-ui font-semibold text-ink-soft">
                Best of {total.toLocaleString("en-CA")} open tech jobs
                {filtering && <span className="font-normal">, {items.length} shown for these filters</span>}
              </h2>
              {items.length ? (
                <ol className="panel grid grid-cols-[minmax(0,1fr)] gap-0.5 p-2">
                  {items.map(({ job, match }) => (
                    <li key={job.id}>
                      <JobCard job={job} headingLevel="h3" />
                      {(match.skills_matched.length > 0 || match.skills_missing.length > 0) && (
                        <p className="-mt-2 px-4 pb-3 pl-[4.6rem] text-sm text-ink-faint">
                          {match.skills_matched.length > 0 && <>You have {match.skills_matched.slice(0, 4).join(", ")}. </>}
                          {match.skills_missing.length > 0 && <>Missing {match.skills_missing.slice(0, 3).join(", ")}.</>}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="card p-6 text-ui text-ink-soft">
                  None of the best-ranked jobs so far fit these filters.{canLoadMore ? " Look further down the ranking below." : ""}
                </p>
              )}
              {canLoadMore && (
                <button type="button" onClick={more} disabled={state === "more"} className="btn btn-secondary btn-lg mt-4 w-full">
                  {state === "more" ? "Loading..." : "Show more"}
                </button>
              )}
            </StaticMatches>
          )}
        </section>

        <aside className="card h-fit space-y-3 p-6" aria-labelledby="score-heading">
          <h2 id="score-heading" className="text-lg font-semibold text-ink">How the score works</h2>
          <dl className="divide-y divide-line">
            {WEIGHTS.map(([label, points]) => (
              <div key={label} className="flex items-center justify-between py-2 text-ui">
                <dt className="text-ink-soft">{label}</dt>
                <dd className="font-semibold text-ink">{points} pts</dd>
              </div>
            ))}
          </dl>
          <p className="text-sm text-ink-soft">
            Read from the whole posting and your whole resume. An estimate, not an applicant tracking system&apos;s verdict.{" "}
            <Link href="/how-it-works" className="link">More detail</Link>
          </p>
        </aside>
      </div>
    </div>
  );
}
