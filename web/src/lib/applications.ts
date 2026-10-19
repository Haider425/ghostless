"use client";

import type { SavedJob } from "./saved";

/*
  "Did you apply?" after a visit to an employer's site.

  Ghostless can't see what happens on the employer's site, so it never
  assumes an application: clicking "Apply" only notes that the person went
  to look (the pending job, in this browser). When they come back, they're
  asked once, and only their answer is recorded.

  - one pending job at a time: the latest Apply click
  - a job they said they applied to is never asked about again in this browser
    (the account's record is also safe to repeat, so another device asking
    again changes nothing)
  - a pending visit older than three days is forgotten

  Storage can be unavailable; then nothing is asked and nothing breaks.
*/

export type ApplyJob = Omit<SavedJob, "savedAt">;
type Pending = { job: ApplyJob; at: number };

const PENDING = "ghostless:apply-pending:v1";
const ANSWERED = "ghostless:apply-answered:v1";
export const APPLY_EVENT = "ghostless:apply";
/** Back sooner than this, and they probably didn't get as far as applying: ask on a later return. */
export const MIN_AWAY_MS = 8_000;
const FORGET_AFTER_MS = 3 * 24 * 60 * 60 * 1000;
const MAX_ANSWERED = 300;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // blocked or full: the prompt simply won't appear
  }
  window.dispatchEvent(new Event(APPLY_EVENT));
}

function appliedIds(): number[] {
  const ids = read<unknown>(ANSWERED, []);
  return Array.isArray(ids) ? ids.filter((id): id is number => typeof id === "number") : [];
}

/** The Apply link was used: remember the job, unless they already said they applied. */
export function noteApplyClick(job: ApplyJob): void {
  if (appliedIds().includes(job.id)) return;
  write(PENDING, { job, at: Date.now() } satisfies Pending);
}

/** The job to ask about now, if any. */
export function pendingApplication(now = Date.now()): Pending | null {
  const pending = read<Pending | null>(PENDING, null);
  if (!pending || typeof pending.job?.id !== "number" || typeof pending.at !== "number") return null;
  if (now - pending.at > FORGET_AFTER_MS || appliedIds().includes(pending.job.id)) {
    write(PENDING, null);
    return null;
  }
  return pending;
}

/** The person answered: "applied" is remembered for good, "not yet" only clears this visit. */
export function answerApplication(jobId: number, answer: "applied" | "not_yet"): void {
  if (answer === "applied") write(ANSWERED, [jobId, ...appliedIds().filter((id) => id !== jobId)].slice(0, MAX_ANSWERED));
  if (read<Pending | null>(PENDING, null)?.job?.id === jobId) write(PENDING, null);
}
