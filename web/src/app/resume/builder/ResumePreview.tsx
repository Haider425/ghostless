import type { CSSProperties, ReactNode } from "react";

import type { ResumeDoc, SectionKey, Template } from "@/lib/resumeDoc";
import { SECTION_LABELS } from "@/lib/resumeDoc";

/*
  The resume itself, as it prints: a single column on a US Letter page,
  real text (not images) so applicant tracking systems can read it.
  Colours are fixed (not theme tokens) because a resume prints the same
  whatever the site's theme.
*/

const STYLES: Record<Template, { font: string; size: number; accent: string; heading: CSSProperties; name: CSSProperties; gap: number }> = {
  classic: {
    font: "Georgia, 'Times New Roman', serif",
    size: 10.5,
    accent: "#111111",
    heading: { borderBottom: "1px solid #111", textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 10.5, fontWeight: 700 },
    name: { textAlign: "center", fontSize: 24, fontWeight: 700 },
    gap: 10,
  },
  modern: {
    font: "'Public Sans Variable', Arial, sans-serif",
    size: 10,
    accent: "#2451c7",
    heading: { color: "#2451c7", fontSize: 11.5, fontWeight: 700, borderBottom: "1.5px solid #d7def0" },
    name: { fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em" },
    gap: 11,
  },
  compact: {
    font: "Arial, Helvetica, sans-serif",
    size: 9.5,
    accent: "#111111",
    heading: { fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "1px solid #999" },
    name: { fontSize: 20, fontWeight: 700 },
    gap: 7,
  },
};

const range = (start: string, end: string) => (start && end ? `${start} – ${end}` : start || end);

function Row({ left, right, sub }: { left: ReactNode; right?: string; sub?: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
      <div style={{ minWidth: 0 }}>
        {left}
        {sub && <span style={{ fontStyle: "italic" }}>{sub}</span>}
      </div>
      {right && <div style={{ whiteSpace: "nowrap", flexShrink: 0 }}>{right}</div>}
    </div>
  );
}

function Bullets({ items }: { items: string[] }) {
  const shown = items.filter((b) => b.trim());
  if (!shown.length) return null;
  return (
    <ul style={{ margin: "2px 0 0", paddingLeft: 16, listStyle: "disc" }}>
      {shown.map((b, i) => (
        <li key={i} style={{ marginTop: 1 }}>
          {b}
        </li>
      ))}
    </ul>
  );
}

export function ResumePreview({ doc }: { doc: ResumeDoc }) {
  const s = STYLES[doc.template];
  const c = doc.contact;
  const contactLine = [c.email, c.phone, c.location, ...c.links.map((l) => l.url)].filter(Boolean);

  const sections: Record<SectionKey, ReactNode> = {
    summary: doc.summary.trim() ? <p style={{ margin: 0 }}>{doc.summary}</p> : null,
    education: doc.education.some((e) => e.school || e.degree)
      ? doc.education.map((e, i) => (
          <div key={i} style={{ marginTop: i ? 5 : 0 }}>
            <Row left={<strong>{e.school}</strong>} right={e.location} />
            <Row left={<span>{e.degree}</span>} right={range(e.start, e.end)} />
            <Bullets items={e.details} />
          </div>
        ))
      : null,
    experience: doc.experience.some((e) => e.title || e.company)
      ? doc.experience.map((e, i) => (
          <div key={i} style={{ marginTop: i ? 6 : 0 }}>
            <Row left={<strong>{e.title}</strong>} right={range(e.start, e.end)} />
            <Row left={<span style={{ fontStyle: "italic" }}>{e.company}</span>} right={e.location} />
            <Bullets items={e.bullets} />
          </div>
        ))
      : null,
    projects: doc.projects.some((p) => p.name)
      ? doc.projects.map((p, i) => (
          <div key={i} style={{ marginTop: i ? 6 : 0 }}>
            <Row
              left={
                <>
                  <strong>{p.name}</strong>
                  {p.tech && <span> | {p.tech}</span>}
                </>
              }
              right={p.date}
            />
            {p.link && <div style={{ color: "#444" }}>{p.link}</div>}
            <Bullets items={p.bullets} />
          </div>
        ))
      : null,
    skills: doc.skills.some((g) => g.items.trim())
      ? doc.skills
          .filter((g) => g.items.trim())
          .map((g, i) => (
            <div key={i}>
              {g.label && <strong>{g.label}: </strong>}
              {g.items}
            </div>
          ))
      : null,
    certifications: doc.certifications.some((x) => x.name)
      ? doc.certifications.map((x, i) => <Row key={i} left={<strong>{x.name}</strong>} sub={x.issuer ? `, ${x.issuer}` : undefined} right={x.date} />)
      : null,
  };

  return (
    <div
      style={{
        fontFamily: s.font,
        fontSize: s.size,
        lineHeight: 1.35,
        color: "#111",
        background: "#fff",
        width: "8.5in",
        minHeight: "11in",
        padding: "0.55in 0.6in",
        boxSizing: "border-box",
      }}
    >
      <header style={{ marginBottom: s.gap }}>
        <div style={s.name}>{c.name || "Your name"}</div>
        {c.headline && <div style={{ textAlign: s.name.textAlign, color: "#333", marginTop: 2 }}>{c.headline}</div>}
        {contactLine.length > 0 && (
          <div style={{ textAlign: s.name.textAlign, color: "#333", marginTop: 4 }}>{contactLine.join("  |  ")}</div>
        )}
      </header>
      {doc.section_order.map((key) =>
        sections[key] ? (
          <section key={key} style={{ marginTop: s.gap }}>
            <h2 style={{ ...s.heading, margin: "0 0 4px", paddingBottom: 2, fontFamily: s.font }}>{SECTION_LABELS[key]}</h2>
            {sections[key]}
          </section>
        ) : null,
      )}
    </div>
  );
}
