"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ApplyLink } from "@/components/ApplyLink";
import { CompanyLogo } from "@/components/CompanyLogo";
import { CloseIcon, ExternalIcon, PinIcon } from "@/components/Icons";
import { RiskBadge } from "@/components/RiskBadge";
import type { ApplicationStatus, SavedEntry } from "@/lib/api-types";
import { TIME_ZONE, ago, possessive, shortLocation } from "@/lib/format";
import { useSavedJobs } from "@/lib/saved";

const STATUSES: { value: ApplicationStatus; label: string }[] = [
  { value: "saved", label: "Interested" },
  { value: "applied", label: "Applied" },
  { value: "interviewing", label: "Interviewing" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Not moving forward" },
];

const STATUS_STYLE: Record<ApplicationStatus, string> = {
  saved: "bg-neutral-tint text-ink-soft",
  applied: "bg-accent-tint text-accent",
  interviewing: "bg-ochre-tint text-ochre",
  offer: "bg-good-tint text-good",
  rejected: "bg-sunken text-ink-faint",
};

export function EmptySaved() {
  return (
    <div className="rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
      <h2 className="font-display text-xl font-semibold text-ink">Nothing saved yet</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-ink-soft">
        Use the bookmark on any job to keep it here while you decide where to apply.
      </p>
      <Link
        href="/jobs"
        className="btn btn-primary mt-5"
      >
        Browse jobs
      </Link>
    </div>
  );
}

/** "2026-09-02" in Toronto time, for a date input; empty when not recorded. */
function dateInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(iso),
  );
}

async function patch(
  jobId: number,
  body: { status?: ApplicationStatus; notes?: string; applied_at?: string | null },
): Promise<boolean> {
  try {
    const response = await fetch(`/api/saved?id=${jobId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** Saved jobs on the account, as an application tracker. */
export function Tracker({ initial, failed }: { initial: SavedEntry[]; failed: boolean }) {
  const [entries, setEntries] = useState(initial);
  const [filter, setFilter] = useState<ApplicationStatus | "all">("all");
  const [error, setError] = useState<string | null>(failed ? "Your saved jobs couldn't load. Refresh to try again." : null);
  const { toggle } = useSavedJobs();

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: entries.length };
    for (const e of entries) c[e.status] = (c[e.status] ?? 0) + 1;
    return c;
  }, [entries]);
  const shown = filter === "all" ? entries : entries.filter((e) => e.status === filter);

  function update(jobId: number, change: Partial<SavedEntry>) {
    setEntries((list) => list.map((e) => (e.job.id === jobId ? { ...e, ...change } : e)));
  }

  async function setStatus(entry: SavedEntry, status: ApplicationStatus) {
    const before = entry.status;
    // moving to applied records today, as the server does
    update(entry.job.id, { status, ...(status === "applied" && !entry.applied_at && { applied_at: new Date().toISOString() }) });
    if (!(await patch(entry.job.id, { status }))) {
      update(entry.job.id, { status: before });
      setError("That change didn't save. Check your connection and try again.");
    }
  }

  async function setAppliedDate(entry: SavedEntry, day: string) {
    const before = entry.applied_at ?? null;
    const next = day ? new Date(`${day}T12:00:00Z`).toISOString() : null;
    update(entry.job.id, { applied_at: next });
    if (!(await patch(entry.job.id, { applied_at: day || null }))) {
      update(entry.job.id, { applied_at: before });
      setError("That date didn't save. Try again.");
    }
  }

  async function saveNotes(entry: SavedEntry, notes: string) {
    if ((entry.notes ?? "") === notes) return;
    update(entry.job.id, { notes });
    if (!(await patch(entry.job.id, { notes }))) setError("Your notes didn't save. Try again.");
  }

  async function remove(entry: SavedEntry) {
    setEntries((list) => list.filter((e) => e.job.id !== entry.job.id));
    await toggle({
      id: entry.job.id,
      title: entry.job.title,
      company: entry.job.company,
      companyDomain: entry.job.company_domain ?? null,
      location: entry.job.location,
      url: entry.job.url,
    });
  }

  if (entries.length === 0 && !failed) return <EmptySaved />;

  return (
    <div className="space-y-4">
      {error && (
        <p role="alert" className="rounded-lg bg-brick-tint px-4 py-2.5 text-sm text-brick">
          {error}
        </p>
      )}
      <div role="tablist" aria-label="Filter by status" className="flex flex-wrap gap-2">
        {[{ value: "all" as const, label: "All" }, ...STATUSES].map(({ value, label }) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={filter === value}
            onClick={() => setFilter(value)}
            className="btn btn-secondary btn-sm aria-selected:border-accent aria-selected:bg-accent-tint aria-selected:text-accent"
          >
            {label}
            <span className="text-xs text-ink-faint">{counts[value] ?? 0}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line-strong p-6 text-sm text-ink-soft">
          No applications with this status.
        </p>
      ) : (
        <ul className="space-y-3">
          {shown.map((entry) => {
            const job = entry.job;
            return (
              <li key={job.id} className="rounded-xl border border-line bg-surface p-4">
                <div className="flex items-start gap-3">
                  <CompanyLogo name={job.company} domain={job.company_domain} />
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <h2 className="font-sans text-base font-semibold text-ink">
                      <Link href={`/jobs/${job.id}`} className="hover:text-accent hover:underline">
                        {job.title}
                      </Link>
                    </h2>
                    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-soft">
                      <span className="font-medium text-ink">{job.company}</span>
                      <span className="inline-flex items-center gap-1">
                        <PinIcon className="size-3.5 text-ink-faint" />
                        {shortLocation(job.location)}
                      </span>
                      <span>Saved {ago(entry.saved_at)}</span>
                      {!job.is_active && <span className="font-medium text-brick">Posting closed</span>}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <label className="sr-only" htmlFor={`status-${job.id}`}>
                        Status for {job.title}
                      </label>
                      <select
                        id={`status-${job.id}`}
                        value={entry.status}
                        onChange={(e) => setStatus(entry, e.target.value as ApplicationStatus)}
                        className={`h-8 rounded-full border-0 px-3 text-sm font-medium ${STATUS_STYLE[entry.status]}`}
                      >
                        {STATUSES.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                      <RiskBadge risk={job.signals.risk} />
                      {entry.status !== "saved" && (
                        <label className="inline-flex items-center gap-1.5 text-sm text-ink-soft">
                          Applied on
                          <input
                            type="date"
                            value={dateInputValue(entry.applied_at)}
                            max={dateInputValue(new Date().toISOString())}
                            onChange={(e) => setAppliedDate(entry, e.target.value)}
                            aria-label={`Date you applied to ${job.title}`}
                            className="field h-8 w-auto px-2 text-sm"
                          />
                          {!entry.applied_at && <span className="text-xs text-ink-faint">not recorded</span>}
                        </label>
                      )}
                      {job.is_active && (
                        <ApplyLink
                          job={{
                            id: job.id,
                            title: job.title,
                            company: job.company,
                            companyDomain: job.company_domain ?? null,
                            location: job.location,
                            url: job.url,
                          }}
                          className="inline-flex items-center gap-1 text-sm link"
                        >
                          Apply on {possessive(job.company)} site
                          <ExternalIcon className="size-3.5" />
                          <span className="sr-only"> (opens in a new tab)</span>
                        </ApplyLink>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => remove(entry)}
                    className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-faint hover:bg-sunken hover:text-brick"
                  >
                    <CloseIcon className="size-4" />
                    <span className="sr-only">Remove {job.title} from saved jobs</span>
                  </button>
                </div>
                <details className="mt-3 border-t border-line pt-3" open={Boolean(entry.notes)}>
                  <summary className="text-sm font-medium text-ink-soft hover:text-ink">
                    {entry.notes ? "Notes" : "Add notes"}
                  </summary>
                  <label htmlFor={`notes-${job.id}`} className="sr-only">
                    Notes for {job.title}
                  </label>
                  <textarea
                    id={`notes-${job.id}`}
                    defaultValue={entry.notes ?? ""}
                    maxLength={2000}
                    rows={3}
                    placeholder="Recruiter's name, interview dates, what to prepare..."
                    onBlur={(e) => saveNotes(entry, e.target.value)}
                    className="field mt-2 py-2 text-sm"
                  />
                  <p className="text-xs text-ink-faint">Saved when you click away.</p>
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
