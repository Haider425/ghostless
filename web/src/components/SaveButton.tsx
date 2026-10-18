"use client";

import { type SavedJob, useSavedJobs } from "@/lib/saved";

import { BookmarkIcon } from "./Icons";

type Props = { job: Omit<SavedJob, "savedAt">; variant?: "icon" | "button" };

/** Saves a job in this browser. Rendered as a real button, so it's reachable by keyboard. */
export function SaveButton({ job, variant = "icon" }: Props) {
  const { isSaved, toggle } = useSavedJobs();
  const saved = isSaved(job.id);
  const label = saved ? `Remove ${job.title} from saved jobs` : `Save ${job.title}`;

  if (variant === "button") {
    return (
      <button
        type="button"
        onClick={() => toggle(job)}
        aria-pressed={saved}
        className="inline-flex h-11 items-center gap-2 rounded-lg border border-line-strong bg-surface px-4 font-medium text-ink transition-colors hover:border-accent hover:text-accent aria-pressed:border-accent aria-pressed:bg-accent-tint aria-pressed:text-accent"
      >
        <BookmarkIcon className="size-4" filled={saved} />
        {saved ? "Saved" : "Save"}
        <span className="sr-only"> {job.title}</span>
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={() => toggle(job)}
      aria-pressed={saved}
      aria-label={label}
      title={saved ? "Saved" : "Save"}
      className="relative z-10 grid size-9 shrink-0 place-items-center rounded-lg text-ink-faint transition-colors hover:bg-sunken hover:text-accent aria-pressed:text-accent"
    >
      <BookmarkIcon className="size-[18px]" filled={saved} />
    </button>
  );
}
