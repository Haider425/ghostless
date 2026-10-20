import type { ReactNode } from "react";

/** A long-form page (policies, methodology): a readable column with numbered-free sections. */
export function ProsePage({ title, intro, updated, children }: { title: string; intro: ReactNode; updated?: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-20 sm:px-6">
      <header className="mb-12">
        <h1 className="page-title">{title}</h1>
        <p className="page-lead">{intro}</p>
        {updated && <p className="mt-3 text-sm text-ink-faint">Last updated {updated}</p>}
      </header>
      <div className="space-y-12">{children}</div>
    </div>
  );
}

export function ProseSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-8 space-y-3">
      <h2 id={`${id}-title`} className="text-3xl font-bold tracking-[-0.02em] text-ink">
        {title}
      </h2>
      <div className="space-y-4 text-[1.0625rem] leading-7 text-ink-soft [&_li]:pl-1 [&_strong]:font-semibold [&_strong]:text-ink [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}
