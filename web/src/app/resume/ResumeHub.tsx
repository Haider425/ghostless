"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type DragEvent, useRef, useState } from "react";

import { GhostMascot } from "@/components/GhostMascot";
import type { Analysis, ResumeCheck, ResumeSummary } from "@/lib/api-types";
import { formatDate, pluralize } from "@/lib/format";
import { clearLocalResume, refreshAccountResume, saveLocalResume, useActiveResume } from "@/lib/resume";

const STAGE: Record<string, string> = {
  student: "a student",
  new_grad: "a new grad",
  experienced: "an experienced candidate",
  senior: "a senior candidate",
};
const ROLE: Record<string, string> = {
  sde: "software",
  data_eng: "data engineering",
  data: "data and analytics",
  ml: "AI and ML",
  hardware: "hardware and embedded",
  security: "security",
};
const GROUPS: { severity: ResumeCheck["severity"]; title: string; chip: string }[] = [
  { severity: "high", title: "Fix first", chip: "chip-bad" },
  { severity: "medium", title: "Worth fixing", chip: "chip-warn" },
  { severity: "low", title: "Polish", chip: "chip-neutral" },
];

type Tone = "good" | "warn" | "bad";

function scoreTone(score: number): Tone {
  if (score >= 85) return "good";
  if (score >= 50) return "warn";
  return "bad";
}

function verdict(score: number) {
  if (score >= 85) return "Strong resume";
  if (score >= 70) return "Good, with a few fixes";
  if (score >= 50) return "Needs some work";
  return "Needs work";
}

function experience(months: number) {
  if (months < 1) return "no dated work experience yet";
  if (months < 12) return `${pluralize(months, "month")} of experience`;
  const years = Math.round((months / 12) * 10) / 10;
  return `about ${years} ${years === 1 ? "year" : "years"} of experience`;
}

const RING: Record<Tone, string> = { good: "var(--b-green)", warn: "var(--ochre)", bad: "var(--brick)" };
const BACKDROP: Record<Tone, string> = { good: "bg-b-mint", warn: "bg-b-butter", bad: "bg-b-blush" };

function ScoreRing({ score }: { score: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative size-32 shrink-0">
      <svg viewBox="0 0 120 120" className="size-full" role="img" aria-label={`Resume strength ${score} out of 100`}>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--hover)" strokeWidth="9" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke={RING[scoreTone(score)]}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div aria-hidden="true" className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-4xl leading-none font-bold text-ink tabular-nums">{score}</span>
        <span className="mt-1 text-xs font-medium text-ink-soft">out of 100</span>
      </div>
    </div>
  );
}

function Upload({ signedIn, onDone }: { signedIn: boolean; onDone: (title: string, analysis: Analysis) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [save, setSave] = useState(true);
  const [state, setState] = useState<"idle" | "reading" | "error">("idle");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);

  async function send(file: File) {
    setState("reading");
    setError("");
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`/api/resume/analyze${signedIn && save ? "?save=1" : ""}`, { method: "POST", body: form }).catch(() => null);
    const data = (await response?.json().catch(() => null)) as (Analysis & { detail?: string }) | null;
    if (!response?.ok || !data?.profile) {
      setError(data?.detail ?? "That didn't work. Check your connection and try again.");
      setState("error");
      return;
    }
    setState("idle");
    onDone(file.name.replace(/\.[^.]+$/, ""), data);
  }

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void send(file);
    e.target.value = "";
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void send(file);
  };

  const reading = state === "reading";
  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-2xl border-2 border-dashed px-6 py-10 text-center shadow-soft transition-colors sm:px-10 sm:py-12 ${
          dragging ? "border-accent bg-accent-tint" : "border-line-strong bg-surface"
        }`}
      >
        <GhostMascot className={`mx-auto h-24 w-21 ${reading ? "ghost-float" : ""}`} />
        <p className="mt-4 font-display text-2xl font-bold text-ink" aria-live="polite">
          {reading ? "Reading your resume…" : "Drop your resume here"}
        </p>
        <p className="mt-1 text-sm text-ink-soft">
          {reading ? "Checking it the way recruiters and job postings will." : "PDF or Word (.docx), up to 5 MB."}
        </p>
        <button type="button" onClick={() => input.current?.click()} disabled={reading} className="btn btn-primary btn-lg mt-6">
          {reading ? "Analyzing…" : "Choose a file"}
        </button>
        <input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only" onChange={onPick} aria-label="Resume file" />
      </div>
      {state === "error" && <p role="alert" className="notice notice-danger">{error}</p>}
      {signedIn ? (
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} className="size-4 accent-[var(--accent)]" />
          Save it to my account so my matches follow me (only the text is kept, never the file)
        </label>
      ) : (
        <p className="text-sm text-ink-soft">
          Your file is read on our server and not kept. The results stay in this browser.{" "}
          <Link href="/signup?next=/resume" className="text-accent hover:underline">Create an account</Link> to keep them on every device.
        </p>
      )}
    </div>
  );
}

const STEPS = [
  { tint: "bg-b-mint text-b-green", text: "A strength score and the fixes that matter most, in order" },
  { tint: "bg-b-sky text-accent", text: "A match score on every job, read from the whole posting: each requirement checked, and what to change" },
  { tint: "bg-b-butter text-ochre", text: "Jobs ranked by how well you fit, with likely ghost jobs left out" },
];

function WhatYouGet({ onCancel }: { onCancel?: () => void }) {
  return (
    <aside className="card p-6 sm:p-7">
      <h2 className="font-display text-xl font-bold text-ink">What you&apos;ll get</h2>
      <ol className="mt-4 space-y-4">
        {STEPS.map((step, i) => (
          <li key={step.text} className="flex gap-3">
            <span className={`flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${step.tint}`}>{i + 1}</span>
            <span className="pt-0.5 text-sm text-ink">{step.text}</span>
          </li>
        ))}
      </ol>
      <p className="mt-5 border-t border-line pt-4 text-sm text-ink-soft">
        No resume yet? <Link href="/resume/builder" className="link">Build one</Link> in a few minutes, with a clean layout recruiters and
        applicant tracking systems can read.
      </p>
      {onCancel && (
        <button type="button" onClick={onCancel} className="mt-3 text-sm link">
          Cancel and keep the current one
        </button>
      )}
    </aside>
  );
}

type ReportActions = { builderHref: string; builderLabel: string; onReplace: () => void; onRemove?: () => void };

function Report({ title, analysis, actions }: { title: string; analysis: Analysis; actions: ReportActions }) {
  const p = analysis.profile;
  const skills = p.skills ?? [];
  const checks = analysis.checks;
  const tone = scoreTone(analysis.strength);
  const graduation = typeof p.education?.graduation === "string" ? p.education.graduation : null;
  return (
    <div className="space-y-5">
      <section aria-labelledby="resume-verdict" className="card p-6 sm:p-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:gap-8">
          <ScoreRing score={analysis.strength} />
          <div className="min-w-0 flex-1">
            <p className="label">Resume strength</p>
            <h2 id="resume-verdict" className="mt-1 font-display text-3xl leading-tight font-bold tracking-tight text-ink">
              {verdict(analysis.strength)}
            </h2>
            <p className="mt-2 max-w-xl text-ink-soft">
              Reads as {STAGE[p.level] ?? p.level} aiming at {ROLE[p.top_role] ?? "tech"} work, with {experience(p.months_experience)}.
              {graduation &&
                ` ${p.education?.still_studying ? "Graduating" : "Graduated"} ${formatDate(`${graduation}-15T12:00:00Z`).replace(/ \d+,/, "")}.`}
            </p>
            <p className="mt-3">
              <span className={`chip chip-md ${checks.length ? (tone === "bad" ? "chip-bad" : "chip-warn") : "chip-good"}`}>
                {checks.length ? `${pluralize(checks.length, "fix", "fixes")} below` : "Nothing major to fix"}
              </span>
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-2">
              <Link href="/resume/matches" className="btn btn-primary">
                See jobs that fit you
              </Link>
              <button type="button" onClick={actions.onReplace} className="btn btn-secondary">
                Upload a new version
              </button>
              <Link href={actions.builderHref} className="btn btn-ghost">
                {actions.builderLabel}
              </Link>
            </div>
          </div>
          <div className={`hidden size-40 shrink-0 items-center justify-center rounded-full md:flex ${BACKDROP[tone]}`}>
            <GhostMascot className="h-28 w-25" />
          </div>
        </div>
      </section>

      <div className={checks.length ? "grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]" : ""}>
        {checks.length > 0 && (
          <section className="card p-6 sm:p-7">
            <h2 className="font-display text-xl font-bold text-ink">What to fix</h2>
            <p className="mt-0.5 text-sm text-ink-soft">Most important first. Each fix raises your score.</p>
            <div className="mt-6 space-y-7">
              {GROUPS.map(({ severity, title: groupTitle, chip }) => {
                const group = checks.filter((c) => c.severity === severity);
                if (!group.length) return null;
                return (
                  <div key={severity}>
                    <h3 className={`chip ${chip}`}>
                      {groupTitle} <span className="tabular-nums">· {group.length}</span>
                    </h3>
                    <ul className="mt-1 divide-y divide-line">
                      {group.map((c) => (
                        <li key={c.id} className="py-4">
                          <p className="font-semibold text-ink">{c.title}</p>
                          <p className="mt-1 text-sm text-ink-soft">{c.detail}</p>
                          {(c.examples ?? []).length > 0 && (
                            <ul className="mt-3 space-y-1.5">
                              {(c.examples ?? []).map((e) => (
                                <li key={e} className="rounded-xl bg-sunken px-3.5 py-2.5 text-sm text-ink">
                                  &ldquo;{e}&rdquo;
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        <section className="card p-6 sm:p-7">
          <div className="flex items-center gap-2">
            <h2 className="font-display text-xl font-bold text-ink">Skills found</h2>
            <span className="chip chip-neutral tabular-nums">{skills.length}</span>
          </div>
          <p className="mt-0.5 text-sm text-ink-soft">What job matching reads from your resume.</p>
          {skills.length ? (
            <ul className="mt-4 flex flex-wrap gap-1.5">
              {skills.map((s) => (
                <li key={s} className="tag">
                  {s}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 rounded-xl bg-sunken px-4 py-3 text-sm text-ink">
              None recognized yet. Add a skills line that names your tools the way postings do.
            </p>
          )}
          <p className="mt-5 border-t border-line pt-3 text-xs text-ink-soft">
            From &ldquo;{title}&rdquo;. Missing a skill? Name it the way postings do, like &ldquo;PostgreSQL&rdquo; or &ldquo;React&rdquo;.
            {actions.onRemove && (
              <>
                {" "}
                <button type="button" onClick={actions.onRemove} className="font-medium underline-offset-2 hover:text-danger hover:underline">
                  Remove it from this browser
                </button>
              </>
            )}
          </p>
        </section>
      </div>
    </div>
  );
}

function SavedResumes({ resumes, activeId }: { resumes: ResumeSummary[]; activeId: number | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  async function act(id: number, action: "primary" | "delete") {
    if (action === "delete" && !window.confirm("Delete this resume? This can't be undone.")) return;
    setBusy(id);
    await fetch(`/api/resumes/${id}${action === "primary" ? "/primary" : ""}`, { method: action === "primary" ? "POST" : "DELETE" }).catch(() => null);
    await refreshAccountResume();
    router.refresh();
    setBusy(null);
  }
  return (
    <section className="card p-6 sm:p-7">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-bold text-ink">Your resumes</h2>
        <Link href="/resume/builder?new=1" className="text-sm link">Build a new one</Link>
      </div>
      <ul className="divide-y divide-line">
        {resumes.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-4">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                <span className="truncate">{r.title}</span>
                {r.id === activeId && <span className="chip chip-good">Used for matching</span>}
              </p>
              <p className="mt-0.5 text-sm text-ink-soft">
                {r.kind === "built" ? "Made in the builder" : (r.file_name ?? "Uploaded")}, updated {formatDate(r.updated_at)}
                {typeof r.strength === "number" && `, strength ${r.strength}`}
              </p>
            </div>
            <div className="flex gap-2 text-sm">
              {r.kind === "built" ? (
                <Link href={`/resume/builder?id=${r.id}`} className="rounded-lg px-2.5 py-1.5 font-medium text-accent hover:bg-accent-tint">Edit</Link>
              ) : (
                <Link href={`/resume/builder?from=${r.id}`} className="rounded-lg px-2.5 py-1.5 font-medium text-accent hover:bg-accent-tint">
                  Edit in builder<span className="sr-only">: {r.title}</span>
                </Link>
              )}
              {r.id !== activeId && (
                <button type="button" disabled={busy === r.id} onClick={() => act(r.id, "primary")} className="rounded-lg px-2.5 py-1.5 font-medium text-ink hover:bg-sunken">
                  Use for matching
                </button>
              )}
              <button type="button" disabled={busy === r.id} onClick={() => act(r.id, "delete")} className="rounded-lg px-2.5 py-1.5 text-ink-soft hover:bg-danger-tint hover:text-danger">
                Delete<span className="sr-only"> {r.title}</span>
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ResumeHub({ signedIn, resumes }: { signedIn: boolean; resumes: ResumeSummary[] }) {
  const router = useRouter();
  const { resume, ready } = useActiveResume();
  const [replacing, setReplacing] = useState(false);
  const [fresh, setFresh] = useState<{ title: string; analysis: Analysis } | null>(null);

  async function onAnalyzed(title: string, analysis: Analysis) {
    setFresh({ title, analysis });
    setReplacing(false);
    if (signedIn) {
      // signed in, the resume lives on the account only, never in this browser
      if (analysis.resume_id) {
        await refreshAccountResume();
        router.refresh();
      }
    } else {
      saveLocalResume(title, analysis);
    }
  }

  const shown = fresh ?? (resume ? { title: resume.title, analysis: resume.analysis } : null);
  // The resume on screen, when it's on the account: the builder opens it (an upload opens as a builder copy).
  // In this browser only the analysis is kept, not the text, so the builder starts from its own draft.
  const shownId = fresh ? (fresh.analysis.resume_id ?? null) : (resume?.id ?? null);

  if (!ready) return <div className="card h-64 animate-pulse" aria-busy="true" />;

  return (
    <div className="space-y-6">
      {shown && !replacing ? (
        <Report
          title={shown.title}
          analysis={shown.analysis}
          actions={{
            builderHref: shownId ? `/resume/builder?id=${shownId}` : "/resume/builder",
            builderLabel: shownId ? "Edit in the builder" : "Open the builder",
            onReplace: () => setReplacing(true),
            onRemove: signedIn
              ? undefined
              : () => {
                  clearLocalResume();
                  setFresh(null);
                },
          }}
        />
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Upload signedIn={signedIn} onDone={onAnalyzed} />
          <WhatYouGet onCancel={replacing ? () => setReplacing(false) : undefined} />
        </div>
      )}
      {signedIn && resumes.length > 0 && <SavedResumes resumes={resumes} activeId={resume?.id ?? null} />}
    </div>
  );
}
