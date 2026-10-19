"use client";

import Link from "next/link";

import { ApplyLink } from "@/components/ApplyLink";
import { CompanyLogo } from "@/components/CompanyLogo";
import { CloseIcon, ExternalIcon, PinIcon } from "@/components/Icons";
import { ago, possessive, shortLocation } from "@/lib/format";
import { useSavedJobs } from "@/lib/saved";

import { EmptySaved } from "./Tracker";

/** Jobs saved in this browser by a signed-out visitor. */
export function SavedList() {
  const { local, removeLocal } = useSavedJobs();
  if (local.length === 0) return <EmptySaved />;

  return (
    <>
      <h2 className="mb-3 font-sans text-sm font-semibold text-ink">
        {local.length} saved {local.length === 1 ? "job" : "jobs"}
      </h2>
      <ul className="space-y-3">
        {local.map((job) => (
          <li key={job.id} className="flex items-start gap-3 rounded-xl border border-line bg-surface p-4">
            <CompanyLogo name={job.company} domain={job.companyDomain} />
            <div className="min-w-0 flex-1">
              <h3 className="font-sans text-base font-semibold text-ink">
                <Link href={`/jobs/${job.id}`} className="hover:text-accent hover:underline">
                  {job.title}
                </Link>
              </h3>
              <p className="flex flex-wrap items-center gap-x-3 text-sm text-ink-soft">
                <span className="font-medium text-ink">{job.company}</span>
                <span className="inline-flex items-center gap-1">
                  <PinIcon className="size-3.5 text-ink-faint" />
                  {shortLocation(job.location)}
                </span>
                <span>Saved {ago(job.savedAt)}</span>
              </p>
              <ApplyLink job={job} className="mt-2 inline-flex items-center gap-1 text-sm link">
                Apply on {possessive(job.company)} site
                <ExternalIcon className="size-3.5" />
                <span className="sr-only"> (opens in a new tab)</span>
              </ApplyLink>
            </div>
            <button
              type="button"
              onClick={() => removeLocal(job.id)}
              className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-faint hover:bg-sunken hover:text-brick"
            >
              <CloseIcon className="size-4" />
              <span className="sr-only">Remove {job.title} from saved jobs</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
