/*
  The resume builder's document: the same shape the API stores and
  validates (tracker/resume/document.py), plus helpers shared by the editor
  and the preview.
*/

export type Template = "classic" | "modern" | "compact";
export type SectionKey = "summary" | "education" | "experience" | "projects" | "skills" | "certifications";

export interface Link {
  label: string;
  url: string;
}
export interface Contact {
  name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  links: Link[];
}
export interface Education {
  school: string;
  degree: string;
  location: string;
  start: string;
  end: string;
  details: string[];
}
export interface Experience {
  title: string;
  company: string;
  location: string;
  start: string;
  end: string;
  bullets: string[];
}
export interface Project {
  name: string;
  tech: string;
  link: string;
  date: string;
  bullets: string[];
}
export interface SkillGroup {
  label: string;
  items: string;
}
export interface Certification {
  name: string;
  issuer: string;
  date: string;
}

export interface ResumeDoc {
  template: Template;
  contact: Contact;
  summary: string;
  education: Education[];
  experience: Experience[];
  projects: Project[];
  skills: SkillGroup[];
  certifications: Certification[];
  section_order: SectionKey[];
}

export const SECTION_LABELS: Record<SectionKey, string> = {
  summary: "Summary",
  education: "Education",
  experience: "Experience",
  projects: "Projects",
  skills: "Skills",
  certifications: "Certifications",
};

export const DEFAULT_ORDER: SectionKey[] = ["education", "experience", "projects", "skills", "summary", "certifications"];

export const blankEducation = (): Education => ({ school: "", degree: "", location: "", start: "", end: "", details: [] });
export const blankExperience = (): Experience => ({ title: "", company: "", location: "", start: "", end: "", bullets: [""] });
export const blankProject = (): Project => ({ name: "", tech: "", link: "", date: "", bullets: [""] });
export const blankSkills = (): SkillGroup => ({ label: "", items: "" });
export const blankCertification = (): Certification => ({ name: "", issuer: "", date: "" });

export function emptyDoc(): ResumeDoc {
  return {
    template: "classic",
    contact: { name: "", headline: "", email: "", phone: "", location: "", links: [{ label: "LinkedIn", url: "" }, { label: "GitHub", url: "" }] },
    summary: "",
    education: [blankEducation()],
    experience: [blankExperience()],
    projects: [blankProject()],
    skills: [{ label: "Languages", items: "" }, { label: "Tools", items: "" }],
    certifications: [],
    section_order: DEFAULT_ORDER,
  };
}

/** A filled-in example, to show what a strong student resume looks like. Fictional. */
export function exampleDoc(): ResumeDoc {
  return {
    template: "classic",
    contact: {
      name: "Jordan Lee",
      headline: "Computer Science student, software and data",
      email: "jordan.lee@example.com",
      phone: "416-555-0199",
      location: "Toronto, ON",
      links: [
        { label: "LinkedIn", url: "linkedin.com/in/jordanlee" },
        { label: "GitHub", url: "github.com/jordanlee" },
      ],
    },
    summary: "",
    education: [
      {
        school: "University of Waterloo",
        degree: "Bachelor of Computer Science, minor in Statistics",
        location: "Waterloo, ON",
        start: "Sep 2023",
        end: "Expected Apr 2027",
        details: ["GPA 3.7, Dean's List", "Courses: Data Structures, Databases, Distributed Systems"],
      },
    ],
    experience: [
      {
        title: "Software Developer Co-op",
        company: "Maple Ledger Bank",
        location: "Toronto, ON",
        start: "May 2025",
        end: "Aug 2025",
        bullets: [
          "Built a React and TypeScript dashboard used by 40 analysts, cutting weekly report time by 30%",
          "Automated nightly SQL Server checks with Python, saving the team 6 hours a week",
          "Designed REST APIs in C# for 3 internal tools, with unit tests covering 85% of new code",
        ],
      },
      {
        title: "Data Engineering Intern",
        company: "Northwind Systems",
        location: "Remote",
        start: "Jan 2026",
        end: "Apr 2026",
        bullets: [
          "Migrated 12 Airflow pipelines to Spark, reducing runtime by 45%",
          "Added data quality alerts that caught 9 bad loads before they reached reports",
        ],
      },
    ],
    projects: [
      {
        name: "Job market tracker",
        tech: "Python, PostgreSQL, FastAPI, Next.js",
        link: "github.com/jordanlee/tracker",
        date: "2026",
        bullets: ["Collects 30,000 postings a day from 50 employers and flags likely ghost jobs"],
      },
    ],
    skills: [
      { label: "Languages", items: "Python, TypeScript, Java, C#, SQL" },
      { label: "Tools", items: "React, Next.js, FastAPI, PostgreSQL, Airflow, Spark, Docker, AWS, Git" },
    ],
    certifications: [],
    section_order: DEFAULT_ORDER,
  };
}

/** Accept a stored or pasted document, filling anything missing. */
export function normalizeDoc(value: unknown): ResumeDoc {
  const base = emptyDoc();
  if (!value || typeof value !== "object") return base;
  const v = value as Partial<ResumeDoc>;
  const order = Array.isArray(v.section_order) ? v.section_order.filter((s): s is SectionKey => s in SECTION_LABELS) : [];
  return {
    template: v.template === "modern" || v.template === "compact" ? v.template : "classic",
    contact: { ...base.contact, ...(v.contact ?? {}), links: v.contact?.links ?? base.contact.links },
    summary: v.summary ?? "",
    education: v.education ?? [],
    experience: v.experience ?? [],
    projects: v.projects ?? [],
    skills: v.skills ?? [],
    certifications: v.certifications ?? [],
    section_order: [...order, ...DEFAULT_ORDER.filter((s) => !order.includes(s))],
  };
}

/** Drop empty entries and bullets before saving, so the API's limits aren't hit by blanks. */
export function cleanDoc(doc: ResumeDoc): ResumeDoc {
  const nonEmpty = <T extends object>(items: T[]) =>
    items.filter((item) => Object.values(item).some((v) => (Array.isArray(v) ? v.some((x) => String(x).trim()) : String(v).trim())));
  const bullets = (list: string[]) => list.map((b) => b.trim()).filter(Boolean);
  return {
    ...doc,
    contact: { ...doc.contact, links: doc.contact.links.filter((l) => l.url.trim()) },
    education: nonEmpty(doc.education).map((e) => ({ ...e, details: bullets(e.details) })),
    experience: nonEmpty(doc.experience).map((e) => ({ ...e, bullets: bullets(e.bullets) })),
    projects: nonEmpty(doc.projects).map((p) => ({ ...p, bullets: bullets(p.bullets) })),
    skills: doc.skills.filter((s) => s.items.trim()),
    certifications: nonEmpty(doc.certifications),
  };
}

const range = (start: string, end: string) => (start && end ? `${start} - ${end}` : start || end);

/** Plain text, laid out like tracker.resume.document.document_to_text, for analysis. */
export function docToText(doc: ResumeDoc): string {
  const c = doc.contact;
  const lines = [c.name, c.headline, [c.email, c.phone, c.location].filter(Boolean).join(" | "), ...c.links.map((l) => l.url).filter(Boolean)];
  for (const section of doc.section_order) {
    if (section === "summary" && doc.summary.trim()) lines.push("", "Summary", doc.summary.trim());
    if (section === "education" && doc.education.length) {
      lines.push("", "Education");
      for (const e of doc.education) {
        lines.push([e.school, e.degree, e.location, range(e.start, e.end)].filter(Boolean).join(" | "));
        lines.push(...e.details.filter((d) => d.trim()).map((d) => `• ${d}`));
      }
    }
    if (section === "experience" && doc.experience.length) {
      lines.push("", "Experience");
      for (const e of doc.experience) {
        lines.push([e.title, e.company, e.location, range(e.start, e.end)].filter(Boolean).join(" | "));
        lines.push(...e.bullets.filter((b) => b.trim()).map((b) => `• ${b}`));
      }
    }
    if (section === "projects" && doc.projects.length) {
      lines.push("", "Projects");
      for (const p of doc.projects) {
        lines.push([p.name, p.tech, p.link, p.date].filter(Boolean).join(" | "));
        lines.push(...p.bullets.filter((b) => b.trim()).map((b) => `• ${b}`));
      }
    }
    if (section === "skills" && doc.skills.some((s) => s.items.trim())) {
      lines.push("", "Skills", ...doc.skills.filter((s) => s.items.trim()).map((s) => (s.label ? `${s.label}: ${s.items}` : s.items)));
    }
    if (section === "certifications" && doc.certifications.length) {
      lines.push("", "Certifications", ...doc.certifications.map((x) => [x.name, x.issuer, x.date].filter(Boolean).join(" | ")));
    }
  }
  return lines.join("\n").trim();
}

// ---------- bullet tips (the same rules as the server's checks) ----------

const WEAK = /^(responsible\s+for|helped|assisted|worked\s+on|participated\s+in|involved\s+in|tasked\s+with|duties\s+included|in\s+charge\s+of|was\s+part\s+of|helping|working\s+on|did|handled)\b/i;
const NUMBER = /\d|%|\$|\b(one|two|three|four|five|ten|hundred|thousand|million|billion)\b/i;
const PRONOUN = /^(i|my|me)\b/i;

const ING_START = /^[A-Z]?[a-z]+ing\b/;
const VAGUE = /\b(various|several|many|some|etc\.?|stuff|things|a lot of|lots of|multiple)\b/i;
const FILLER = /\b(successfully|effectively|efficiently|actively|really|very)\b/i;
const OUTCOME = /\b(by|to|so|which|resulting|reducing|reduced|cutting|cut|saving|saved|increasing|increased|improving|improved|enabling|letting|allowing|used by|serving|for \d|in under|under \d|down to|within)\b/i;
const PRESENT = /^(build|develop|design|write|create|manage|maintain|lead|work|help|test|implement)s?\b/i;

export interface BulletTip {
  text: string;
  kind: "fix" | "idea";
}

/** Coaching for one bullet, most important first. An empty list means it reads well. */
export function bulletCoach(bullet: string, current = false): BulletTip[] {
  const text = bullet.trim();
  if (!text) return [];
  const words = text.split(/\s+/);
  const tips: BulletTip[] = [];
  if (WEAK.test(text)) tips.push({ kind: "fix", text: "Start with what you did, not your duty: built, designed, automated, led." });
  else if (PRONOUN.test(text)) tips.push({ kind: "fix", text: "Drop “I” and start with the verb." });
  else if (ING_START.test(text)) tips.push({ kind: "fix", text: "Use the past tense (“Built”, not “Building”) so it reads as done." });
  else if (!current && PRESENT.test(text)) tips.push({ kind: "fix", text: "Finished work reads better in the past tense: “Built”, not “Build”." });
  if (!NUMBER.test(text)) tips.push({ kind: "fix", text: "Add a number: users, requests a day, time saved, size of the data, or a percentage." });
  if (VAGUE.test(text)) tips.push({ kind: "idea", text: `Swap “${text.match(VAGUE)?.[0]}” for the exact count or names.` });
  if (FILLER.test(text)) tips.push({ kind: "idea", text: `“${text.match(FILLER)?.[0]}” adds nothing; the result shows it.` });
  if (words.length >= 8 && !OUTCOME.test(text)) tips.push({ kind: "idea", text: "Say what it led to: “..., cutting report time by 30%” or “..., used by 40 analysts”." });
  if (words.length > 35) tips.push({ kind: "fix", text: `${words.length} words. Aim for one or two lines (under 30).` });
  else if (words.length < 6) tips.push({ kind: "idea", text: "Very short. Add what you used and what changed because of it." });
  return tips;
}

export function bulletTips(bullet: string): string[] {
  return bulletCoach(bullet).map((t) => t.text);
}
