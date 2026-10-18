import type { ReactNode } from "react";

/** A long-form page (policies, methodology): a readable column with numbered-free sections. */
export function ProsePage({ title, intro, updated, children }: { title: string; intro: ReactNode; updated?: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-10 space-y-3">
        <h1 className="text-3xl font-semibold text-ink">{title}</h1>
        <p className="text-lg text-ink-soft">{intro}</p>
        {updated && <p className="text-sm text-ink-faint">Last updated {updated}</p>}
      </header>
      <div className="space-y-10">{children}</div>
    </div>
  );
}

export function ProseSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-8 space-y-3">
      <h2 id={`${id}-title`} className="text-2xl font-semibold text-ink">
        {title}
      </h2>
      <div className="space-y-3 leading-relaxed text-ink-soft [&_li]:pl-1 [&_strong]:font-semibold [&_strong]:text-ink [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}
