"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { JobCard } from "@/components/JobCard";
import { StaticMatches } from "@/components/Match";
import { useSite } from "@/components/SiteContext";
import type { Match, Recommendation, RecommendationPage } from "@/lib/api-types";
import { type ActiveResume, resumeQuery, useActiveResume } from "@/lib/resume";

const LOCATIONS = [
  { value: "any", label: "Anywhere" },
  { value: "canada", label: "In Canada" },
  { value: "remote", label: "Remote" },
  { value: "canada_or_remote", label: "Canada or remote" },
] as const;
type Loc = (typeof LOCATIONS)[number]["value"];

async function load(resume: ActiveResume, location: Loc, includeRisky: boolean, offset: number): Promise<RecommendationPage | null> {
  const response = await fetch("/api/resume/recommendations", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...resumeQuery(resume), location, include_high_risk: includeRisky, offset }),
  }).catch(() => null);
  return response?.ok ? ((await response.json()) as RecommendationPage) : null;
}

export function Matches() {
  const { resume, ready } = useActiveResume();
  const { prefs } = useSite();
  const [location, setLocation] = useState<Loc>(prefs.default_location);
  const [risky, setRisky] = useState(false);
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
    void load(resume, location, risky, 0).then((page) => {
      if (live) setData({ resume, location, risky, items: page?.items ?? [], total: page?.total ?? 0, failed: !page });
    });
    return () => {
      live = false;
    };
  }, [resume, location, risky]);

  const current = data && data.resume === resume && data.location === location && data.risky === risky ? data : null;
  const items = current?.items ?? [];
  const total = current?.total ?? 0;
  const state: "loading" | "ready" | "more" | "error" = !current
    ? "loading"
    : current.failed
      ? "error"
      : loadingMore
        ? "more"
        : "ready";

  async function more() {
    if (!resume || !current) return;
    setLoadingMore(true);
    const page = await load(resume, location, risky, items.length);
    if (page) setData({ ...current, items: [...current.items, ...page.items] });
    setLoadingMore(false);
  }

  if (!ready) return <div className="mt-8 h-64 animate-pulse rounded-2xl bg-sunken" aria-busy="true" />;
  if (!resume) {
    return (
      <div className="mt-8 rounded-2xl border border-dashed border-line-strong bg-surface p-10 text-center">
        <p className="font-display text-xl font-semibold text-ink">Add your resume first</p>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-soft">Upload a PDF or Word file, or build one, and your matches appear here.</p>
        <div className="mt-5 flex justify-center gap-3">
          <Link href="/resume" className="inline-flex h-11 items-center rounded-lg bg-accent px-5 font-medium text-on-accent">Upload resume</Link>
          <Link href="/resume/builder" className="inline-flex h-11 items-center rounded-lg border border-line-strong px-5 font-medium text-ink">Build one</Link>
        </div>
      </div>
    );
  }

  const scores: Record<number, Match> = Object.fromEntries(items.map((r) => [r.job.id, r.match]));

  return (
    <div className="mt-8 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4">
        <p className="text-sm text-ink-soft">
          Matching <span className="font-medium text-ink">&ldquo;{resume.title}&rdquo;</span>.{" "}
          <Link href="/resume" className="text-accent hover:underline">Change</Link>
        </p>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2 text-ink-soft">
            Location
            <select value={location} onChange={(e) => setLocation(e.target.value as Loc)} className="h-9 rounded-lg border border-line-strong bg-surface px-2 text-ink">
              {LOCATIONS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-ink-soft">
            <input type="checkbox" checked={risky} onChange={(e) => setRisky(e.target.checked)} className="size-4 accent-[var(--accent)]" />
            Include high ghost risk
          </label>
        </div>
      </div>

      {state === "error" && <p role="alert" className="rounded-lg bg-brick-tint px-3 py-2 text-sm text-brick">Matches couldn&apos;t load. Try again in a moment.</p>}
      {state === "loading" ? (
        <div className="space-y-3" aria-busy="true">
          {Array.from({ length: 5 }, (_, i) => <div key={i} className="h-32 animate-pulse rounded-xl border border-line bg-surface" />)}
        </div>
      ) : (
        <StaticMatches scores={scores}>
          <h2 className="font-sans text-sm font-semibold text-ink">
            Best of {total.toLocaleString("en-CA")} open tech jobs
          </h2>
          <ol className="space-y-3">
            {items.map(({ job, match }) => (
              <li key={job.id} className="space-y-0">
                <JobCard job={job} headingLevel="h3" />
                {(match.skills_matched.length > 0 || match.skills_missing.length > 0) && (
                  <p className="-mt-1 rounded-b-xl border border-t-0 border-line bg-sunken px-4 pt-3 pb-2.5 text-xs text-ink-soft">
                    {match.skills_matched.length > 0 && <>You have {match.skills_matched.slice(0, 4).join(", ")}. </>}
                    {match.skills_missing.length > 0 && <>Missing {match.skills_missing.slice(0, 3).join(", ")}.</>}
                  </p>
                )}
              </li>
            ))}
          </ol>
          {items.length < total && items.length < 1000 && (
            <button type="button" onClick={more} disabled={state === "more"} className="h-11 w-full rounded-xl border border-line-strong bg-surface font-medium text-ink hover:border-ink-faint disabled:opacity-60">
              {state === "more" ? "Loading..." : "Show more"}
            </button>
          )}
        </StaticMatches>
      )}
    </div>
  );
}
