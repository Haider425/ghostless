"use client";

import Link from "next/link";
import { type ReactNode, createContext, useContext, useEffect, useState } from "react";

import type { AIFeedback, Match } from "@/lib/api-types";
import { fetchMatches, scoreTone, useActiveResume } from "@/lib/resume";

import { useSite } from "./SiteContext";

/* Resume match scores: a badge on job cards, and a full panel on job pages. */

const MatchContext = createContext<Record<number, Match>>({});

/** Fetches match scores for the jobs on a page, once, if the visitor has a resume. */
export function MatchScores({ jobIds, children }: { jobIds: number[]; children: ReactNode }) {
  const { resume } = useActiveResume();
  const [scores, setScores] = useState<Record<number, Match>>({});
  const key = jobIds.join(",");
  useEffect(() => {
    if (!resume || !key) return;
    let live = true;
    void fetchMatches(resume, key.split(",").map(Number)).then((s) => live && setScores(s));
    return () => {
      live = false;
    };
  }, [resume, key]);
  return <MatchContext.Provider value={scores}>{children}</MatchContext.Provider>;
}

/** For pages that already have the scores (recommendations). */
export function StaticMatches({ scores, children }: { scores: Record<number, Match>; children: ReactNode }) {
  return <MatchContext.Provider value={scores}>{children}</MatchContext.Provider>;
}

/** The score in a job row's side slot: a small ring under the save button, so it never shifts the row. */
export function MatchBadge({ jobId }: { jobId: number }) {
  const match = useContext(MatchContext)[jobId];
  if (!match) return null;
  return (
    <span title={`${match.score}% match: ${match.label}`} className="block">
      <Ring score={match.score} size="sm" />
      <span className="sr-only">{match.score}% match: {match.label}</span>
    </span>
  );
}

/** A score from 0 to 100 as a ring with the number inside. */
export function Ring({ score, label, size = "md" }: { score: number; label?: string; size?: "sm" | "md" | "lg" }) {
  const r = 27;
  const c = 2 * Math.PI * r;
  const tone = scoreTone(score);
  const stroke = tone === "strong" || tone === "good" ? "var(--accent-solid)" : "var(--ink-faint)";
  const box = { sm: "size-10", md: "size-14", lg: "size-20" }[size];
  return (
    <svg viewBox="0 0 64 64" className={`${box} shrink-0`} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <circle cx="32" cy="32" r={r} fill="none" stroke="var(--hover)" strokeWidth="5" />
      <circle
        cx="32"
        cy="32"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={`${(score / 100) * c} ${c}`}
        transform="rotate(-90 32 32)"
      />
      <text x="32" y="32" dy="0.36em" textAnchor="middle" fontSize={size === "sm" ? 20 : 19} fontWeight="650" fill="var(--ink)">
        {score}
      </text>
    </svg>
  );
}

const STATUS = {
  met: { mark: "✓", label: "Have it", tone: "text-accent" },
  partial: { mark: "◐", label: "Partly", tone: "text-accent" },
  missing: { mark: "✕", label: "Missing", tone: "text-ink-faint" },
} as const;

type Requirement = NonNullable<Match["requirements"]>[number];

function Breakdown({ match }: { match: Match }) {
  const parts = match.breakdown ?? [];
  if (!parts.length) return null;
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-ink">Where the points come from</h4>
      <ul className="space-y-2.5">
        {parts.map((p) => (
          <li key={p.key} className="text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium text-ink">{p.label}</span>
              <span className="shrink-0 tabular-nums text-ink-soft">
                {Math.round(p.points)} <span className="text-ink-faint">of {p.max}</span>
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sunken" aria-hidden="true">
              <div className="h-full rounded-full bg-accent-solid" style={{ width: `${Math.min(100, (p.points / p.max) * 100)}%` }} />
            </div>
            <p className="mt-1 text-xs text-ink-soft">{p.detail}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Checklist({ items }: { items: Requirement[] }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  // missing first, then partly met, then met
  const order = { missing: 0, partial: 1, met: 2 } as const;
  const sorted = [...items].sort((a, b) => order[a.status] - order[b.status] || Number(a.kind === "preferred") - Number(b.kind === "preferred"));
  const shown = all ? sorted : sorted.slice(0, 8);
  const met = items.filter((r) => r.status === "met").length;
  return (
    <div>
      <h4 className="mb-1 text-sm font-semibold text-ink">What the posting asks for</h4>
      <p className="mb-2 text-xs text-ink-soft">
        You fully meet {met} of {items.length}.
      </p>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {shown.map((r) => (
          <li key={`${r.kind}:${r.text}`} className="flex items-start gap-3 px-3 py-2 text-sm">
            <span aria-hidden="true" className={`mt-px w-4 shrink-0 text-center font-semibold ${STATUS[r.status].tone}`}>
              {STATUS[r.status].mark}
            </span>
            <span className="min-w-0 flex-1">
              <span className="font-medium text-ink">{r.text}</span>
              {r.kind === "preferred" && <span className="ml-1.5 text-xs text-ink-faint">nice to have</span>}
              <span className="block text-xs text-ink-soft">
                <span className="sr-only">{STATUS[r.status].label}. </span>
                {r.detail}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {sorted.length > 8 && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 text-sm text-accent hover:underline">
          {all ? "Show fewer" : `Show all ${sorted.length}`}
        </button>
      )}
    </div>
  );
}

function Terms({ matched, missing }: { matched: string[]; missing: string[] }) {
  if (!matched.length && !missing.length) return null;
  return (
    <div>
      <h4 className="mb-1 text-sm font-semibold text-ink">The posting&apos;s key terms</h4>
      <p className="mb-2 text-xs text-ink-soft">Words it repeats for the work itself. Use them where they&apos;re true for you.</p>
      <ul className="flex flex-wrap gap-1.5 text-xs">
        {matched.map((t) => (
          <li key={t} className="rounded-full bg-accent-tint px-2.5 py-1 text-accent">
            <span className="sr-only">On your resume: </span>✓ {t}
          </li>
        ))}
        {missing.map((t) => (
          <li key={t} className="rounded-full border border-dashed border-line-strong px-2.5 py-1 text-ink-soft">
            <span className="sr-only">Not on your resume: </span>
            {t}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The full match for one job: score, what matches, what's missing, what to change. */
export function MatchPanel({ jobId, hasDescription, headingAs = "h2" }: { jobId: number; hasDescription: boolean; headingAs?: "h2" | "h3" }) {
  const Heading = headingAs;
  const { resume, ready } = useActiveResume();
  // the result remembers which resume and job it scored, so a stale one is never shown
  const [result, setResult] = useState<{ resume: unknown; jobId: number; match: Match | null } | null>(null);

  useEffect(() => {
    if (!resume) return;
    let live = true;
    void fetchMatches(resume, [jobId]).then((s) => {
      if (live) setResult({ resume, jobId, match: s[jobId] ?? null });
    });
    return () => {
      live = false;
    };
  }, [resume, jobId]);

  const fresh = result && result.resume === resume && result.jobId === jobId ? result : null;
  const match = fresh?.match ?? null;
  const loading = Boolean(resume) && !fresh;

  const box = "record-box";
  if (!ready) return <div className={`${box} h-40 animate-pulse`} aria-busy="true" />;
  if (!resume) {
    return (
      <section className={`${box} space-y-3`}>
        <Heading className="panel-title">How well do you match?</Heading>
        <p className="text-sm text-ink-soft">
          Upload your resume to get a match score for this job, the skills you&apos;re missing, and what to change. Free, and it
          stays in your browser unless you save it to an account.
        </p>
        <Link href="/resume" className="btn btn-primary">
          Upload your resume
        </Link>
      </section>
    );
  }
  if (loading) return <div className={`${box} h-40 animate-pulse`} aria-busy="true" aria-label="Scoring your resume" />;
  if (!match) {
    return (
      <section className={box}>
        <Heading className="panel-title">How well do you match?</Heading>
        <p className="mt-2 text-sm text-ink-soft">This job couldn&apos;t be scored right now. Try again in a moment.</p>
      </section>
    );
  }

  return (
    <section aria-label="Your match" className={`${box} space-y-4`}>
      <div className="flex items-center gap-4">
        <Ring score={match.score} />
        <div className="min-w-0">
          <Heading className="font-sans text-base font-semibold tracking-normal text-ink">{match.label}</Heading>
          <p className="text-sm text-ink-soft">
            Your resume &ldquo;{resume.title}&rdquo; against this posting.{" "}
            <Link href="/resume" className="text-accent hover:underline">Change</Link>
          </p>
        </div>
      </div>

      {match.requirements && match.requirements.length > 0 ? (
        <>
          <Checklist items={match.requirements} />
          <Terms matched={match.terms_matched ?? []} missing={match.terms_missing ?? []} />
          <Breakdown match={match} />
        </>
      ) : (
        <>
          <Breakdown match={match} />
          {match.skills_missing.length > 0 && (
            <p className="text-sm">
              <span className="font-medium text-ink">Not on your resume: </span>
              <span className="text-ink-soft">{match.skills_missing.join(", ")}</span>
            </p>
          )}
        </>
      )}

      {match.suggestions.length > 0 && (
        <div className="border-t border-line pt-4">
          <h4 className="mb-2 text-sm font-semibold text-ink">To raise your score</h4>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-soft marker:text-line-strong">
            {match.suggestions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-sm">
        <Link href={`/resume/builder?job=${jobId}${resume.id ? `&id=${resume.id}` : ""}`} className="link">
          Tailor your resume to this job
        </Link>
        <span className="text-ink-soft"> in the builder, with the score updating as you edit.</span>
      </p>
      {match.notes.map((n) => (
        <p key={n} className="text-xs text-ink-faint">{n}</p>
      ))}
      <p className="text-xs text-ink-faint">
        An estimate from the whole posting and your whole resume, not an applicant tracking system&apos;s verdict. Never add skills you don&apos;t have.
      </p>
      {hasDescription && <AIReview jobId={jobId} />}
    </section>
  );
}

function AIReview({ jobId }: { jobId: number }) {
  const { aiEnabled, viewer } = useSite();
  const { resume } = useActiveResume();
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [feedback, setFeedback] = useState<AIFeedback | null>(null);
  const [error, setError] = useState("");
  if (!aiEnabled || !resume) return null;

  if (!viewer) {
    return (
      <p className="border-t border-line pt-4 text-sm text-ink-soft">
        <Link href="/login" className="link">Sign in</Link> for a detailed AI review of your resume
        for this job.
      </p>
    );
  }

  async function run() {
    if (!resume) return;
    setState("loading");
    const response = await fetch("/api/resume/ai-feedback", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ job_id: jobId, resume_id: resume.id }),
    }).catch(() => null);
    const data = (await response?.json().catch(() => null)) as (AIFeedback & { detail?: string }) | null;
    if (response?.ok && data) {
      setFeedback(data);
      setState("done");
    } else {
      setError(data?.detail ?? "The AI review didn't work this time. Try again in a minute.");
      setState("error");
    }
  }

  if (resume.id === null) {
    return (
      <p className="border-t border-line pt-4 text-sm text-ink-soft">
        Save your resume to your account on the <Link href="/resume" className="link">resume page</Link> to
        get a detailed AI review for this job.
      </p>
    );
  }

  return (
    <div className="space-y-3 border-t border-line pt-4">
      {state !== "done" && (
        <>
          <button
            type="button"
            onClick={run}
            disabled={state === "loading"}
            className="btn btn-secondary"
          >
            {state === "loading" ? "Reviewing your resume..." : "Get a detailed AI review"}
          </button>
          <p className="text-xs text-ink-faint">Sends your resume and this posting to an AI model to review. A few per day.</p>
        </>
      )}
      {state === "error" && <p role="alert" className="notice notice-danger">{error}</p>}
      {feedback && (
        <div className="space-y-3 text-sm">
          <p className="text-ink">{feedback.summary}</p>
          {feedback.strengths.length > 0 && (
            <div>
              <h4 className="font-semibold text-ink">What fits</h4>
              <ul className="list-disc pl-5 text-ink-soft">{feedback.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
            </div>
          )}
          {feedback.gaps.length > 0 && (
            <div>
              <h4 className="font-semibold text-ink">Gaps</h4>
              <ul className="list-disc pl-5 text-ink-soft">{feedback.gaps.map((s) => <li key={s}>{s}</li>)}</ul>
            </div>
          )}
          {feedback.rewrites.length > 0 && (
            <div className="space-y-2">
              <h4 className="font-semibold text-ink">Bullets to rework</h4>
              {feedback.rewrites.map((r) => (
                <div key={r.original} className="rounded-lg bg-sunken p-3">
                  <p className="text-ink-faint line-through decoration-ink-faint/40">{r.original}</p>
                  <p className="mt-1 text-ink">{r.improved}</p>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-ink-faint">{feedback.remaining_today} AI reviews left today. AI can be wrong: check every suggestion is true for you.</p>
        </div>
      )}
    </div>
  );
}
