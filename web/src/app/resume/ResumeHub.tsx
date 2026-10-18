"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type DragEvent, useRef, useState } from "react";

import { Ring } from "@/components/Match";
import type { Analysis, ResumeCheck, ResumeSummary } from "@/lib/api-types";
import { formatDate, pluralize } from "@/lib/format";
import { clearLocalResume, refreshAccountResume, saveLocalResume, useActiveResume } from "@/lib/resume";

const STAGE: Record<string, string> = {
  student: "Student",
  new_grad: "New grad",
  experienced: "Experienced",
  senior: "Senior",
};
const ROLE: Record<string, string> = {
  sde: "Software",
  data_eng: "Data engineering",
  data: "Data and analytics",
  ml: "AI and ML",
  hardware: "Hardware and embedded",
  security: "Security",
};
const GROUPS: { severity: ResumeCheck["severity"]; title: string }[] = [
  { severity: "high", title: "Fix first" },
  { severity: "medium", title: "Worth fixing" },
  { severity: "low", title: "Polish" },
];

function strengthLabel(score: number) {
  if (score >= 85) return "Strong";
  if (score >= 70) return "Good, with a few fixes";
  if (score >= 50) return "Needs some work";
  return "Needs work";
}

function experience(months: number) {
  if (months < 1) return "No dated work experience found";
  if (months < 12) return `${pluralize(months, "month")} of experience`;
  const years = Math.round((months / 12) * 10) / 10;
  return `About ${years} ${years === 1 ? "year" : "years"} of experience`;
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

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-2xl border-2 border-dashed p-8 text-center transition-colors sm:p-10 ${
          dragging ? "border-accent bg-accent-tint" : "border-line-strong bg-surface"
        }`}
      >
        <p className="font-display text-xl font-semibold text-ink">
          {state === "reading" ? "Reading your resume..." : "Drop your resume here"}
        </p>
        <p className="mt-1 text-sm text-ink-soft">PDF or Word (.docx), up to 5 MB.</p>
        <button
          type="button"
          onClick={() => input.current?.click()}
          disabled={state === "reading"}
          className="btn btn-primary btn-lg mt-5"
        >
          {state === "reading" ? "Analyzing..." : "Choose a file"}
        </button>
        <input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only" onChange={onPick} aria-label="Resume file" />
      </div>
      {state === "error" && <p role="alert" className="rounded-lg bg-brick-tint px-3 py-2 text-sm text-brick">{error}</p>}
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

function Report({ title, analysis }: { title: string; analysis: Analysis }) {
  const p = analysis.profile;
  return (
    <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
      <section className="space-y-5 panel p-6">
        <div className="flex items-center gap-4">
          <Ring score={analysis.strength} label={`Resume strength ${analysis.strength} out of 100`} />
          <div>
            <h2 className="font-sans text-base font-semibold text-ink">Resume strength</h2>
            <p className="text-sm text-ink-soft">{strengthLabel(analysis.strength)}</p>
          </div>
        </div>
        <dl className="space-y-3 border-t border-line pt-4 text-sm">
          <div>
            <dt className="text-ink-soft">Reads as</dt>
            <dd className="font-medium text-ink">
              {STAGE[p.level] ?? p.level}, {ROLE[p.top_role] ?? "tech"} work
            </dd>
          </div>
          <div>
            <dt className="text-ink-soft">Experience</dt>
            <dd className="font-medium text-ink">{experience(p.months_experience)}</dd>
          </div>
          {typeof p.education?.graduation === "string" && (
            <div>
              <dt className="text-ink-soft">{p.education?.still_studying ? "Graduating" : "Graduated"}</dt>
              <dd className="font-medium text-ink">{formatDate(`${p.education.graduation}-15T12:00:00Z`).replace(/ \d+,/, "")}</dd>
            </div>
          )}
          <div>
            <dt className="mb-1.5 text-ink-soft">Skills found ({(p.skills ?? []).length})</dt>
            <dd className="flex flex-wrap gap-1.5">
              {(p.skills ?? []).length ? (
                (p.skills ?? []).map((s) => (
                  <span key={s} className="rounded-md bg-sunken px-2 py-0.5 text-xs text-ink">
                    {s}
                  </span>
                ))
              ) : (
                <span className="text-ink-faint">None recognized</span>
              )}
            </dd>
          </div>
        </dl>
        <p className="border-t border-line pt-4 text-xs text-ink-faint">From &ldquo;{title}&rdquo;. Missing a skill? Name it the way postings do, like &ldquo;PostgreSQL&rdquo; or &ldquo;React&rdquo;.</p>
      </section>

      <section className="space-y-5 panel p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-sans text-base font-semibold text-ink">What to improve</h2>
            <p className="text-sm text-ink-soft">
              {analysis.checks.length ? `${pluralize(analysis.checks.length, "suggestion")}, most important first.` : "Nothing major. Nice work."}
            </p>
          </div>
          <Link href="/resume/matches" className="btn btn-primary">
            See jobs that fit you
          </Link>
        </div>
        {GROUPS.map(({ severity, title: groupTitle }) => {
          const checks = analysis.checks.filter((c) => c.severity === severity);
          if (!checks.length) return null;
          return (
            <div key={severity}>
              <h3 className="mb-2 font-sans text-sm font-semibold text-ink-soft">{groupTitle}</h3>
              <ul className="space-y-3">
                {checks.map((c) => (
                  <li
                    key={c.id}
                    className={`border-l-2 pl-3 ${severity === "high" ? "border-brick" : severity === "medium" ? "border-ochre" : "border-line-strong"}`}
                  >
                    <p className="font-medium text-ink">{c.title}</p>
                    <p className="text-sm text-ink-soft">{c.detail}</p>
                    {(c.examples ?? []).length > 0 && (
                      <ul className="mt-1.5 space-y-1">
                        {(c.examples ?? []).map((e) => (
                          <li key={e} className="rounded-md bg-sunken px-2.5 py-1.5 text-sm text-ink">
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
      </section>
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
    <section className="panel p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-sans text-base font-semibold text-ink">Your resumes</h2>
        <Link href="/resume/builder?new=1" className="text-sm link">Build a new one</Link>
      </div>
      <ul className="divide-y divide-line">
        {resumes.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-ink">
                {r.title}{" "}
                {r.id === activeId && <span className="ml-1 rounded-full bg-accent-tint px-2 py-0.5 text-xs font-medium text-accent">Used for matching</span>}
              </p>
              <p className="text-sm text-ink-soft">
                {r.kind === "built" ? "Made in the builder" : (r.file_name ?? "Uploaded")}, updated {formatDate(r.updated_at)}
                {typeof r.strength === "number" && `, strength ${r.strength}`}
              </p>
            </div>
            <div className="flex gap-2 text-sm">
              {r.kind === "built" ? (
                <Link href={`/resume/builder?id=${r.id}`} className="rounded-md px-2.5 py-1.5 font-medium text-accent hover:bg-accent-tint">Edit</Link>
              ) : (
                <Link href={`/resume/builder?from=${r.id}`} className="rounded-md px-2.5 py-1.5 font-medium text-accent hover:bg-accent-tint">
                  Edit in builder<span className="sr-only">: {r.title}</span>
                </Link>
              )}
              {r.id !== activeId && (
                <button type="button" disabled={busy === r.id} onClick={() => act(r.id, "primary")} className="rounded-md px-2.5 py-1.5 font-medium text-ink hover:bg-sunken">
                  Use for matching
                </button>
              )}
              <button type="button" disabled={busy === r.id} onClick={() => act(r.id, "delete")} className="rounded-md px-2.5 py-1.5 text-ink-soft hover:bg-brick-tint hover:text-brick">
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

  if (!ready) return <div className="h-64 animate-pulse rounded-2xl border border-line bg-surface" aria-busy="true" />;

  return (
    <div className="space-y-6">
      {shown && !replacing ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={() => setReplacing(true)} className="btn btn-secondary">
              Upload a new version
            </button>
            <Link href="/resume/builder" className="btn btn-secondary">
              Open the resume builder
            </Link>
            {!signedIn && (
              <button type="button" onClick={() => { clearLocalResume(); setFresh(null); }} className="text-sm text-ink-soft hover:text-brick hover:underline">
                Remove from this browser
              </button>
            )}
          </div>
          <Report title={shown.title} analysis={shown.analysis} />
        </>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Upload signedIn={signedIn} onDone={onAnalyzed} />
          <aside className="space-y-4 panel p-6 text-sm text-ink-soft">
            <h2 className="font-sans text-base font-semibold text-ink">What you&apos;ll get</h2>
            <ul className="list-disc space-y-1.5 pl-5 marker:text-line-strong">
              <li>A strength score and the fixes that matter most</li>
              <li>A match score on every job, read from the whole posting: each requirement checked, and what to change</li>
              <li>Jobs ranked by how well you fit, without likely ghost jobs</li>
            </ul>
            <p>
              No resume yet? <Link href="/resume/builder" className="link">Build one</Link> in a few
              minutes, with a clean layout recruiters and applicant tracking systems can read.
            </p>
            {replacing && (
              <button type="button" onClick={() => setReplacing(false)} className="text-accent hover:underline">Cancel</button>
            )}
          </aside>
        </div>
      )}
      {signedIn && resumes.length > 0 && <SavedResumes resumes={resumes} activeId={resume?.id ?? null} />}
    </div>
  );
}
