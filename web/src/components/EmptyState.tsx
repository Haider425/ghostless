import type { ReactNode } from "react";

import { GhostMascot } from "./GhostMascot";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card px-6 py-12 text-center">
      <GhostMascot className="mx-auto mb-4 w-16" />
      <h2 className="text-xl font-bold text-ink">{title}</h2>
      {children && <div className="mx-auto mt-2 max-w-md text-ui text-ink-soft">{children}</div>}
    </div>
  );
}
