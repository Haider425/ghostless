import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card px-6 py-14 text-center">
      <h2 className="text-xl font-bold text-ink">{title}</h2>
      {children && <div className="mx-auto mt-2 max-w-md text-ui text-ink-soft">{children}</div>}
    </div>
  );
}
