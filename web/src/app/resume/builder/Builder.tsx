"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { inputClass } from "@/components/Form";
import { useSite } from "@/components/SiteContext";
import { Ring } from "@/components/Match";
import type { Analysis, Match } from "@/lib/api-types";
import { draftKey, refreshAccountResume, saveLocalResume } from "@/lib/resume";
import {
  type ResumeDoc,
  type SectionKey,
  blankCertification,
  blankEducation,
  blankExperience,
  blankProject,
  blankSkills,
  bulletCoach,
  cleanDoc,
  docToText,
  emptyDoc,
  exampleDoc,
  normalizeDoc,
} from "@/lib/resumeDoc";

import { ResumePreview } from "./ResumePreview";

function readDraft(key: string): { doc: ResumeDoc; title?: string } | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { doc: unknown; title?: string };
    return { doc: normalizeDoc(saved.doc), title: saved.title };
  } catch {
    return null; // storage blocked or the draft is unreadable: start fresh
  }
}
const PAGE_WIDTH = 816; // 8.5in at 96px per inch

// ---------- small inputs ----------

function Text({ label, value, onChange, placeholder, wide }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; wide?: boolean }) {
  return (
    <label className={`block space-y-1 ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-xs font-medium text-ink-soft">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className={`${inputClass} h-10`} />
    </label>
  );
}

function BulletList({ label, items, onChange, placeholder, tips = true, current = false }: { label: string; items: string[]; onChange: (v: string[]) => void; placeholder: string; tips?: boolean; current?: boolean }) {
  const list = items.length ? items : [""];
  const set = (i: number, value: string) => onChange(list.map((b, j) => (j === i ? value : b)));
  return (
    <fieldset className="space-y-2 sm:col-span-2">
      <legend className="text-xs font-medium text-ink-soft">{label}</legend>
      {list.map((bullet, i) => {
        const advice = tips ? bulletCoach(bullet, current) : [];
        return (
          <div key={i} className="space-y-1">
            <div className="flex gap-2">
              <span aria-hidden="true" className="pt-2.5 text-ink-faint">•</span>
              <textarea
                value={bullet}
                onChange={(e) => set(i, e.target.value.replace(/\n/g, " "))}
                rows={2}
                placeholder={i === 0 ? placeholder : ""}
                aria-label={`${label} ${i + 1}`}
                className="field min-h-10 resize-y py-2 text-sm"
              />
              <button type="button" onClick={() => onChange(list.filter((_, j) => j !== i))} className="h-9 shrink-0 rounded-md px-2 text-ink-faint hover:bg-sunken hover:text-danger" aria-label={`Remove ${label.toLowerCase()} ${i + 1}`}>
                ×
              </button>
            </div>
            {advice.length > 0 ? (
              <ul className="ml-5 space-y-0.5 text-xs">
                {advice.slice(0, 3).map((a) => (
                  <li key={a.text} className={a.kind === "fix" ? "text-ink" : "text-ink-soft"}>
                    {a.text}
                  </li>
                ))}
              </ul>
            ) : (
              tips &&
              bullet.trim().split(/\s+/).length >= 6 && <p className="ml-5 text-xs text-ink-soft">Reads well: a clear action with a measurable result.</p>
            )}
          </div>
        );
      })}
      {list.length < 8 && (
        <button type="button" onClick={() => onChange([...list, ""])} className="ml-5 text-sm link">
          Add a line
        </button>
      )}
    </fieldset>
  );
}

function Entry({ title, children, onRemove, onUp, onDown }: { title: string; children: ReactNode; onRemove: () => void; onUp?: () => void; onDown?: () => void }) {
  return (
    <div className="rounded-xl border border-line bg-paper p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="truncate text-sm font-semibold text-ink">{title}</p>
        <div className="flex shrink-0 gap-1 text-sm">
          {onUp && <button type="button" onClick={onUp} className="rounded-md px-2 py-1 text-ink-soft hover:bg-sunken" aria-label={`Move ${title} up`}>↑</button>}
          {onDown && <button type="button" onClick={onDown} className="rounded-md px-2 py-1 text-ink-soft hover:bg-sunken" aria-label={`Move ${title} down`}>↓</button>}
          <button type="button" onClick={onRemove} className="rounded-md px-2 py-1 text-ink-soft hover:bg-danger-tint hover:text-danger">Remove</button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </div>
  );
}

function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as T);
  return next;
}

function Section({ id, title, children, onUp, onDown, hint }: { id: string; title: string; children: ReactNode; onUp?: () => void; onDown?: () => void; hint?: string }) {
  return (
    <details open className="group panel" id={id}>
      <summary className="flex items-center justify-between gap-3 px-5 py-4">
        <span>
          <span className="font-sans text-base font-semibold text-ink">{title}</span>
          {hint && <span className="block text-xs text-ink-soft">{hint}</span>}
        </span>
        <span className="flex items-center gap-1 text-sm text-ink-soft">
          {onUp && <button type="button" onClick={(e) => { e.preventDefault(); onUp(); }} className="rounded-md px-2 py-1 hover:bg-sunken" aria-label={`Move ${title} section up`}>↑</button>}
          {onDown && <button type="button" onClick={(e) => { e.preventDefault(); onDown(); }} className="rounded-md px-2 py-1 hover:bg-sunken" aria-label={`Move ${title} section down`}>↓</button>}
          <span aria-hidden="true" className="ml-1 transition-transform group-open:rotate-180">⌄</span>
        </span>
      </summary>
      <div className="space-y-3 border-t border-line px-5 py-4">{children}</div>
    </details>
  );
}

// ---------- preview, scaled to fit ----------

const PAGE_HEIGHT = 1056; // 11in
const LINE = 19; // one line of body text, roughly

function PageFit({ height }: { height: number }) {
  const over = height - PAGE_HEIGHT;
  if (over <= 2) {
    return <p className="mb-2 text-sm text-ink-soft">Fits on one page.</p>;
  }
  const lines = Math.max(1, Math.round(over / LINE));
  const pages = Math.ceil(height / PAGE_HEIGHT);
  return (
    <p className="mb-2 text-sm text-danger">
      {pages > 2 ? `Runs to ${pages} pages.` : `Runs onto a second page by about ${lines} line${lines === 1 ? "" : "s"}.`} Students and new grads do best
      with one page: try the Compact template, or cut the oldest or weakest bullets.
    </p>
  );
}

function ScaledPreview({ doc }: { doc: ResumeDoc }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.6);
  const [height, setHeight] = useState(1056);
  useLayoutEffect(() => {
    const measure = () => {
      if (outer.current) setScale(Math.min(1, outer.current.clientWidth / PAGE_WIDTH));
      if (inner.current) setHeight(inner.current.offsetHeight);
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (outer.current) observer.observe(outer.current);
    if (inner.current) observer.observe(inner.current);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={outer} className="w-full">
      <PageFit height={height} />
      <div style={{ height: height * scale }} className="relative overflow-hidden rounded-lg shadow-pop ring-1 ring-line">
        {Array.from({ length: Math.max(0, Math.ceil(height / PAGE_HEIGHT) - 1) }, (_, i) => (
          <div key={i} aria-hidden="true" className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-dashed border-danger/60" style={{ top: PAGE_HEIGHT * (i + 1) * scale }}>
            <span className="absolute right-2 -translate-y-full bg-danger-tint px-1.5 text-[10px] font-medium text-danger">Page {i + 2}</span>
          </div>
        ))}
        <div ref={inner} className="origin-top-left" style={{ transform: `scale(${scale})`, width: PAGE_WIDTH }}>
          <ResumePreview doc={doc} />
        </div>
      </div>
    </div>
  );
}

// ---------- the builder ----------

type JobPick = { id: number; title: string; company: string; location?: string | null };

export function Builder({
  initial,
  resumeId: initialId,
  initialTitle,
  startEmpty,
  imported = false,
  tailorTo = null,
}: {
  initial: ResumeDoc | null;
  resumeId: number | null;
  initialTitle: string;
  startEmpty: boolean;
  imported?: boolean;
  tailorTo?: JobPick | null;
}) {
  const { viewer } = useSite();
  const router = useRouter();
  // signed out, or a new resume: start from the draft kept in this browser.
  // The builder only renders in the browser (see BuilderClient), so storage is readable here.
  const [draft] = useState(() => (!initial && !startEmpty ? readDraft(draftKey(viewer?.id)) : null));
  const [doc, setDoc] = useState<ResumeDoc>(initial ?? draft?.doc ?? emptyDoc());
  const [title, setTitle] = useState(draft?.title || initialTitle);
  const [resumeId, setResumeId] = useState<number | null>(initialId);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error" | "local">("idle");
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState(imported ? "Your uploaded resume was read into the builder. Resumes come in many layouts, so check each section before saving." : "");
  const [importing, setImporting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  // the toolbar wraps onto more rows on narrower screens: the preview sticks below its real height
  const frame = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const toolbar = bar.current;
    if (!toolbar) return;
    const measure = () => frame.current?.style.setProperty("--builder-bar", `${toolbar.offsetHeight}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(toolbar);
    return () => observer.disconnect();
  }, []);

  async function importFile(file: File) {
    const hasContent = Boolean(doc.contact.name || doc.experience.some((e) => e.title) || doc.education.some((e) => e.school));
    if (hasContent && !window.confirm("Replace what's in the builder with the resume in this file?")) return;
    setImporting(true);
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/resume/to-document", { method: "POST", body: form }).catch(() => null);
    const data = (await response?.json().catch(() => null)) as (ResumeDoc & { detail?: string }) | null;
    setImporting(false);
    if (response?.ok && data) {
      setDoc(normalizeDoc({ ...data, template: doc.template }));
      if (!title || title === "My resume") setTitle(file.name.replace(/\.[^.]+$/, "").slice(0, 80));
      setNotice(`Read ${file.name} into the builder. Resumes come in many layouts, so check each section, then fix anything that landed in the wrong field.`);
    } else {
      setNotice(data?.detail ?? "That file couldn't be read. Try a PDF or Word file with selectable text.");
    }
  }

  // autosave: to the account once saved there, otherwise to this browser
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (resumeId && viewer) {
        setStatus("saving");
        const response = await fetch(`/api/resumes/${resumeId}`, {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ title, document: cleanDoc(doc) }),
        }).catch(() => null);
        setStatus(response?.ok ? "saved" : "error");
      } else {
        try {
          window.localStorage.setItem(draftKey(viewer?.id), JSON.stringify({ doc, title }));
          setStatus("local");
        } catch {
          setStatus("idle");
        }
      }
    }, 1200);
    return () => clearTimeout(timer);
  }, [doc, title, resumeId, viewer]);

  const set = <K extends keyof ResumeDoc>(key: K, value: ResumeDoc[K]) => setDoc((d) => ({ ...d, [key]: value }));
  const setContact = (key: keyof ResumeDoc["contact"], value: string) => setDoc((d) => ({ ...d, contact: { ...d.contact, [key]: value } }));
  const moveSection = (key: SectionKey, by: number) => {
    const i = doc.section_order.indexOf(key);
    set("section_order", move(doc.section_order, i, i + by));
  };

  async function saveToAccount() {
    setStatus("saving");
    const response = await fetch("/api/resumes", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title, document: cleanDoc(doc) }),
    }).catch(() => null);
    if (!response?.ok) return setStatus("error");
    const saved = (await response.json()) as { id: number };
    setResumeId(saved.id);
    setStatus("saved");
    try {
      window.localStorage.removeItem(draftKey(viewer?.id));
    } catch {}
    await refreshAccountResume();
    router.replace(`/resume/builder?id=${saved.id}`, { scroll: false });
  }

  async function check() {
    setChecking(true);
    const text = docToText(cleanDoc(doc));
    const response = await fetch("/api/resume/analyze-text", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    }).catch(() => null);
    const data = (await response?.json().catch(() => null)) as (Analysis & { detail?: string }) | null;
    setChecking(false);
    if (response?.ok && data?.profile) {
      setAnalysis(data);
      // signed out, matches use it right away; signed in, it's used once saved to the account
      if (!viewer) saveLocalResume(title || "Builder resume", data);
    } else {
      setAnalysis(null);
      window.alert(data?.detail ?? "The check didn't work. Try again.");
    }
  }

  const sectionControls = (key: SectionKey) => {
    const i = doc.section_order.indexOf(key);
    return {
      onUp: i > 0 ? () => moveSection(key, -1) : undefined,
      onDown: i < doc.section_order.length - 1 ? () => moveSection(key, 1) : undefined,
    };
  };

  const editors: Record<SectionKey, ReactNode> = {
    summary: (
      <Section id="summary" title="Summary" hint="Optional. Two lines on what you do and want next." {...sectionControls("summary")}>
        <textarea value={doc.summary} onChange={(e) => set("summary", e.target.value)} rows={3} maxLength={600} placeholder="Computer Science student who builds data tools. Looking for a summer 2027 software or data internship." className="field py-2 text-sm" />
      </Section>
    ),
    education: (
      <Section id="education" title="Education" {...sectionControls("education")}>
        {doc.education.map((e, i) => {
          const upd = (patch: Partial<typeof e>) => set("education", doc.education.map((x, j) => (j === i ? { ...x, ...patch } : x)));
          return (
            <Entry key={i} title={e.school || `School ${i + 1}`} onRemove={() => set("education", doc.education.filter((_, j) => j !== i))} onUp={i ? () => set("education", move(doc.education, i, i - 1)) : undefined} onDown={i < doc.education.length - 1 ? () => set("education", move(doc.education, i, i + 1)) : undefined}>
              <Text label="School" value={e.school} onChange={(v) => upd({ school: v })} placeholder="University of Toronto" />
              <Text label="Location" value={e.location} onChange={(v) => upd({ location: v })} placeholder="Toronto, ON" />
              <Text label="Degree" value={e.degree} onChange={(v) => upd({ degree: v })} placeholder="Bachelor of Science, Computer Science" wide />
              <Text label="Start" value={e.start} onChange={(v) => upd({ start: v })} placeholder="Sep 2023" />
              <Text label="End" value={e.end} onChange={(v) => upd({ end: v })} placeholder="Expected Apr 2027" />
              <BulletList label="Details" items={e.details} onChange={(v) => upd({ details: v })} placeholder="GPA, awards, relevant courses" tips={false} />
            </Entry>
          );
        })}
        {doc.education.length < 6 && <button type="button" onClick={() => set("education", [...doc.education, blankEducation()])} className="text-sm link">Add education</button>}
      </Section>
    ),
    experience: (
      <Section id="experience" title="Experience" hint="Jobs, co-ops and internships, newest first." {...sectionControls("experience")}>
        {doc.experience.map((e, i) => {
          const upd = (patch: Partial<typeof e>) => set("experience", doc.experience.map((x, j) => (j === i ? { ...x, ...patch } : x)));
          return (
            <Entry key={i} title={[e.title, e.company].filter(Boolean).join(", ") || `Role ${i + 1}`} onRemove={() => set("experience", doc.experience.filter((_, j) => j !== i))} onUp={i ? () => set("experience", move(doc.experience, i, i - 1)) : undefined} onDown={i < doc.experience.length - 1 ? () => set("experience", move(doc.experience, i, i + 1)) : undefined}>
              <Text label="Job title" value={e.title} onChange={(v) => upd({ title: v })} placeholder="Software Developer Co-op" />
              <Text label="Company" value={e.company} onChange={(v) => upd({ company: v })} placeholder="Company name" />
              <Text label="Location" value={e.location} onChange={(v) => upd({ location: v })} placeholder="Toronto, ON or Remote" wide />
              <Text label="Start" value={e.start} onChange={(v) => upd({ start: v })} placeholder="May 2025" />
              <Text label="End" value={e.end} onChange={(v) => upd({ end: v })} placeholder="Aug 2025 or Present" />
              <BulletList label="What you did" items={e.bullets} onChange={(v) => upd({ bullets: v })} current={/present|current|now/i.test(e.end)} placeholder="Built a dashboard used by 40 analysts, cutting report time by 30%" />
            </Entry>
          );
        })}
        {doc.experience.length < 12 && <button type="button" onClick={() => set("experience", [...doc.experience, blankExperience()])} className="text-sm link">Add a role</button>}
      </Section>
    ),
    projects: (
      <Section id="projects" title="Projects" hint="School, personal or hackathon projects count." {...sectionControls("projects")}>
        {doc.projects.map((p, i) => {
          const upd = (patch: Partial<typeof p>) => set("projects", doc.projects.map((x, j) => (j === i ? { ...x, ...patch } : x)));
          return (
            <Entry key={i} title={p.name || `Project ${i + 1}`} onRemove={() => set("projects", doc.projects.filter((_, j) => j !== i))} onUp={i ? () => set("projects", move(doc.projects, i, i - 1)) : undefined} onDown={i < doc.projects.length - 1 ? () => set("projects", move(doc.projects, i, i + 1)) : undefined}>
              <Text label="Name" value={p.name} onChange={(v) => upd({ name: v })} placeholder="Job market tracker" />
              <Text label="Date" value={p.date} onChange={(v) => upd({ date: v })} placeholder="2026" />
              <Text label="Built with" value={p.tech} onChange={(v) => upd({ tech: v })} placeholder="Python, PostgreSQL, React" wide />
              <Text label="Link" value={p.link} onChange={(v) => upd({ link: v })} placeholder="github.com/you/project" wide />
              <BulletList label="What it does" items={p.bullets} onChange={(v) => upd({ bullets: v })} placeholder="Collects 30,000 postings a day and flags likely ghost jobs" />
            </Entry>
          );
        })}
        {doc.projects.length < 10 && <button type="button" onClick={() => set("projects", [...doc.projects, blankProject()])} className="text-sm link">Add a project</button>}
      </Section>
    ),
    skills: (
      <Section id="skills" title="Skills" hint="Name tools the way postings do: PostgreSQL, React, AWS." {...sectionControls("skills")}>
        {doc.skills.map((g, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[10rem_1fr_auto]">
            <input value={g.label} onChange={(e) => set("skills", doc.skills.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} placeholder="Languages" aria-label={`Skill group ${i + 1} name`} className={`${inputClass} h-10`} />
            <input value={g.items} onChange={(e) => set("skills", doc.skills.map((x, j) => (j === i ? { ...x, items: e.target.value } : x)))} placeholder="Python, SQL, TypeScript" aria-label={`Skill group ${i + 1} skills`} className={`${inputClass} h-10`} />
            <button type="button" onClick={() => set("skills", doc.skills.filter((_, j) => j !== i))} className="h-10 rounded-md px-2 text-sm text-ink-soft hover:bg-danger-tint hover:text-danger">Remove</button>
          </div>
        ))}
        {doc.skills.length < 8 && <button type="button" onClick={() => set("skills", [...doc.skills, blankSkills()])} className="text-sm link">Add a skill group</button>}
      </Section>
    ),
    certifications: (
      <Section id="certifications" title="Certifications" hint="Optional." {...sectionControls("certifications")}>
        {doc.certifications.map((x, i) => {
          const upd = (patch: Partial<typeof x>) => set("certifications", doc.certifications.map((c, j) => (j === i ? { ...c, ...patch } : c)));
          return (
            <Entry key={i} title={x.name || `Certification ${i + 1}`} onRemove={() => set("certifications", doc.certifications.filter((_, j) => j !== i))}>
              <Text label="Name" value={x.name} onChange={(v) => upd({ name: v })} placeholder="AWS Certified Cloud Practitioner" wide />
              <Text label="Issuer" value={x.issuer} onChange={(v) => upd({ issuer: v })} placeholder="Amazon Web Services" />
              <Text label="Date" value={x.date} onChange={(v) => upd({ date: v })} placeholder="2026" />
            </Entry>
          );
        })}
        {doc.certifications.length < 10 && <button type="button" onClick={() => set("certifications", [...doc.certifications, blankCertification()])} className="text-sm link">Add a certification</button>}
      </Section>
    ),
  };

  // the printable copy lives directly in <body>, so printing shows only the resume
  const portal = typeof document === "undefined" ? null : document.body;

  const statusText = {
    idle: "",
    saving: "Saving...",
    saved: "Saved to your account",
    error: "Couldn't save. Check your connection.",
    local: viewer ? "Draft saved in this browser" : "Saved in this browser",
  }[status];

  return (
    <div ref={frame}>
      <div ref={bar} className="sticky top-(--header-h) z-20 -mx-4 mb-6 border-b border-line bg-paper/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-10 lg:px-10">
        <div className="flex flex-wrap items-center gap-3">
          <label className="min-w-0 flex-1">
            <span className="sr-only">Resume name</span>
            <input value={title} onChange={(e) => setTitle(e.target.value.slice(0, 80))} className="h-10 w-full max-w-xs rounded-lg border border-transparent bg-transparent px-2 font-display text-xl font-semibold text-ink hover:border-line focus:border-accent focus:bg-surface focus:outline-none" />
          </label>
          <p aria-live="polite" className="text-sm text-ink-soft">{statusText}</p>
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            Template
            <select value={doc.template} onChange={(e) => set("template", e.target.value as ResumeDoc["template"])} className="h-10 rounded-lg border border-line-strong bg-surface px-2 text-ink">
              <option value="classic">Classic</option>
              <option value="modern">Modern</option>
              <option value="compact">Compact</option>
            </select>
          </label>
          <button type="button" onClick={() => fileInput.current?.click()} disabled={importing} className="btn btn-secondary">
            {importing ? "Reading..." : "Import a file"}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="sr-only"
            tabIndex={-1}
            aria-label="Resume file to import"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void importFile(file);
            }}
          />
          <button type="button" onClick={check} disabled={checking} className="btn btn-secondary">
            {checking ? "Checking..." : "Check my resume"}
          </button>
          <button type="button" onClick={() => window.print()} className="btn btn-secondary">
            Download PDF
          </button>
          {viewer && !resumeId && (
            <button type="button" onClick={saveToAccount} className="btn btn-primary">
              Save to account
            </button>
          )}
          {!viewer && (
            <Link href="/signup?next=/resume/builder" className="btn btn-primary content-center">
              Sign up to save
            </Link>
          )}
        </div>
        <div className="mt-3 flex gap-1 lg:hidden" role="tablist" aria-label="Builder view">
          {(["edit", "preview"] as const).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className="rounded-lg px-3 py-1.5 text-sm font-medium text-ink-soft aria-selected:bg-accent-tint aria-selected:text-accent">
              {t === "edit" ? "Edit" : "Preview"}
            </button>
          ))}
        </div>
      </div>

      {notice && (
        <div role="status" className="mb-6 flex items-start justify-between gap-3 rounded-xl border border-line bg-accent-tint px-4 py-3 text-sm text-ink">
          <p>{notice}</p>
          <button type="button" onClick={() => setNotice("")} className="shrink-0 text-ink-soft hover:underline">Dismiss</button>
        </div>
      )}

      {analysis && (
        <div className="mb-6 panel p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-semibold text-ink">
              Resume strength {analysis.strength} out of 100, with {(analysis.profile.skills ?? []).length} skills recognized
            </p>
            <div className="flex gap-3 text-sm">
              <Link href="/resume/matches" className="link">See jobs that fit</Link>
              <button type="button" onClick={() => setAnalysis(null)} className="text-ink-soft hover:underline">Hide</button>
            </div>
          </div>
          {analysis.checks.length ? (
            <ul className="mt-3 space-y-2 text-sm">
              {analysis.checks.slice(0, 5).map((c) => (
                <li key={c.id} className={`border-l-2 pl-3 ${c.severity === "low" ? "border-line-strong" : "border-accent-solid"}`}>
                  <span className="font-medium text-ink">{c.title}.</span> <span className="text-ink-soft">{c.detail}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-ink-soft">No issues found. Nice work.</p>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
        <div className={`space-y-4 ${tab === "preview" ? "hidden lg:block" : ""}`}>
          <Section id="contact" title="Contact">
            <div className="grid gap-3 sm:grid-cols-2">
              <Text label="Full name" value={doc.contact.name} onChange={(v) => setContact("name", v)} placeholder="Jordan Lee" />
              <Text label="Headline" value={doc.contact.headline} onChange={(v) => setContact("headline", v)} placeholder="Computer Science student" />
              <Text label="Email" value={doc.contact.email} onChange={(v) => setContact("email", v)} placeholder="you@example.com" />
              <Text label="Phone" value={doc.contact.phone} onChange={(v) => setContact("phone", v)} placeholder="416-555-0199" />
              <Text label="City" value={doc.contact.location} onChange={(v) => setContact("location", v)} placeholder="Toronto, ON" wide />
              {doc.contact.links.map((l, i) => (
                <Text key={i} label={l.label || `Link ${i + 1}`} value={l.url} onChange={(v) => set("contact", { ...doc.contact, links: doc.contact.links.map((x, j) => (j === i ? { ...x, url: v } : x)) })} placeholder={l.label === "GitHub" ? "github.com/you" : l.label === "LinkedIn" ? "linkedin.com/in/you" : "yoursite.dev"} />
              ))}
              {doc.contact.links.length < 4 && (
                <button type="button" onClick={() => set("contact", { ...doc.contact, links: [...doc.contact.links, { label: "Website", url: "" }] })} className="text-left text-sm link">
                  Add a link
                </button>
              )}
            </div>
          </Section>
          {doc.section_order.map((key) => <div key={key}>{editors[key]}</div>)}
          <div className="flex flex-wrap gap-3 pt-2 text-sm">
            <button type="button" onClick={() => window.confirm("Replace what you've written with an example resume?") && setDoc(exampleDoc())} className="text-accent hover:underline">
              Load an example
            </button>
            <button type="button" onClick={() => window.confirm("Clear everything and start over?") && setDoc(emptyDoc())} className="text-ink-soft hover:text-danger hover:underline">
              Start over
            </button>
          </div>
        </div>

        {/* below the header and the toolbar; a page taller than the window scrolls inside its column */}
        <div
          className={`scroll-quiet lg:sticky lg:top-[calc(var(--header-h)+var(--builder-bar,4.5rem)+1rem)] lg:max-h-[calc(100dvh-var(--header-h)-var(--builder-bar,4.5rem)-2rem)] lg:overflow-y-auto lg:pr-1 ${tab === "edit" ? "hidden lg:block" : ""}`}
        >
          <TailorPanel doc={doc} initialJob={tailorTo} />
          <h2 className="sr-only">Preview</h2>
          <ScaledPreview doc={doc} />
          {portal && createPortal(<div className="print-portal"><ResumePreview doc={cleanDoc(doc)} /></div>, portal)}
          <p className="mt-3 text-xs text-ink-faint">
            One column of real text, so applicant tracking systems can read it. Download PDF opens your browser&apos;s print
            dialog: choose &ldquo;Save as PDF&rdquo; and turn off headers and footers.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------- tailoring to one job ----------

type Tailored = { match: Match; strength: number };

function TailorPanel({ doc, initialJob }: { doc: ResumeDoc; initialJob: JobPick | null }) {
  const [job, setJob] = useState<JobPick | null>(initialJob);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<JobPick[]>([]);
  const [result, setResult] = useState<{ jobId: number; text: string; data: Tailored | null } | null>(null);
  const text = docToText(cleanDoc(doc));

  // search open jobs by title
  useEffect(() => {
    if (job || query.trim().length < 2) return;
    let live = true;
    const timer = setTimeout(async () => {
      const response = await fetch(`/api/jobs/search?q=${encodeURIComponent(query.trim())}`).catch(() => null);
      const data = (await response?.json().catch(() => null)) as JobPick[] | null;
      if (live) setResults(Array.isArray(data) ? data : []);
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query, job]);

  // rescore a moment after the person stops typing
  useEffect(() => {
    if (!job || text.length < 50) return;
    let live = true;
    const timer = setTimeout(async () => {
      const response = await fetch("/api/resume/tailor", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, job_id: job.id }),
      }).catch(() => null);
      const data = (await response?.json().catch(() => null)) as Tailored | null;
      if (live) setResult({ jobId: job.id, text, data: response?.ok && data?.match ? data : null });
    }, 1200);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [job, text]);

  const box = "mb-4 rounded-2xl border border-line bg-surface p-4";
  if (!job) {
    const shown = query.trim().length >= 2 ? results : [];
    return (
      <section className={box} aria-label="Tailor to a job">
        <h2 className="font-sans text-base font-semibold text-ink">Tailor to a job</h2>
        <p className="mt-1 text-sm text-ink-soft">Pick a posting and see your match change as you edit: what it asks for that your resume doesn&apos;t show yet.</p>
        <label className="mt-3 block">
          <span className="sr-only">Search jobs by title</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search jobs, e.g. data engineering intern" className={`${inputClass} h-10`} />
        </label>
        {shown.length > 0 && (
          <ul className="mt-2 max-h-64 divide-y divide-line overflow-auto rounded-lg border border-line">
            {shown.map((j) => (
              <li key={j.id}>
                <button type="button" onClick={() => setJob(j)} className="block w-full px-3 py-2 text-left text-sm hover:bg-sunken">
                  <span className="font-medium text-ink">{j.title}</span>
                  <span className="block text-xs text-ink-soft">{[j.company, j.location].filter(Boolean).join(", ")}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {query.trim().length >= 2 && !shown.length && <p className="mt-2 text-xs text-ink-faint">No open jobs with that in the title yet.</p>}
      </section>
    );
  }

  const fresh = result && result.jobId === job.id ? result.data : null;
  const stale = !result || result.jobId !== job.id || result.text !== text;
  const match = fresh?.match;
  const gaps = (match?.requirements ?? []).filter((r) => r.status !== "met");
  return (
    <section className={box} aria-label="Tailor to a job">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-ink-soft">Tailoring to</p>
          <h2 className="truncate font-sans text-base font-semibold text-ink">
            <Link href={`/jobs/${job.id}`} className="hover:underline">{job.title}</Link>
          </h2>
          <p className="truncate text-sm text-ink-soft">{job.company}</p>
        </div>
        <button type="button" onClick={() => { setJob(null); setResult(null); }} className="shrink-0 text-sm text-accent hover:underline">
          Change
        </button>
      </div>
      {text.length < 50 ? (
        <p className="mt-3 text-sm text-ink-soft">Add a few sections first, then the score appears here.</p>
      ) : !match ? (
        <div className="mt-3 h-16 animate-pulse rounded-lg bg-sunken" aria-busy="true" aria-label="Scoring" />
      ) : (
        <div className={`mt-3 space-y-3 transition-opacity ${stale ? "opacity-60" : ""}`} aria-live="polite">
          <div className="flex items-center gap-3">
            <Ring score={match.score} label={`${match.score} out of 100`} />
            <div>
              <p className="font-semibold text-ink">{match.label}</p>
              <p className="text-xs text-ink-soft">{stale ? "Updating..." : "Updates as you edit."}</p>
            </div>
          </div>
          {gaps.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold text-ink">Not shown yet</h3>
              <ul className="space-y-1 text-sm">
                {gaps.slice(0, 6).map((r) => (
                  <li key={`${r.kind}:${r.text}`} className="flex gap-2">
                    <span aria-hidden="true" className={r.status === "missing" ? "text-ink-faint" : "text-accent"}>{r.status === "missing" ? "✕" : "◐"}</span>
                    <span>
                      <span className="font-medium text-ink">{r.text}</span> <span className="text-ink-soft">{r.detail.toLowerCase()}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(match.terms_missing ?? []).length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold text-ink">Its key terms you don&apos;t use</h3>
              <ul className="flex flex-wrap gap-1.5 text-xs">
                {(match.terms_missing ?? []).map((t) => (
                  <li key={t} className="rounded-full border border-dashed border-line-strong px-2 py-0.5 text-ink-soft">{t}</li>
                ))}
              </ul>
            </div>
          )}
          {match.suggestions[0] && <p className="text-sm text-ink-soft">{match.suggestions[0]}</p>}
          <p className="text-xs text-ink-faint">Only add what&apos;s true. Recruiters ask about everything on your resume.</p>
        </div>
      )}
    </section>
  );
}
