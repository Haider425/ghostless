"use client";

import type { ReactNode } from "react";

import { type ApplyJob, noteApplyClick } from "@/lib/applications";

/**
 * A link to the employer's own posting. Using it notes the job, so Ghostless
 * can ask "did you apply?" when the person comes back (see ApplyPrompt).
 * Middle-clicks count too; without JavaScript it's a plain link.
 */
export function ApplyLink({ job, className, children }: { job: ApplyJob; className?: string; children: ReactNode }) {
  return (
    <a
      href={job.url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={() => noteApplyClick(job)}
      onAuxClick={(event) => event.button === 1 && noteApplyClick(job)}
      className={className}
    >
      {children}
    </a>
  );
}
