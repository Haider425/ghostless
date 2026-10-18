import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { JobList } from "@/components/JobCard";
import {
  Disclosures,
  JobDescription,
  JobHeader,
  PostingHistory,
  PostingRecord,
  SkillChips,
} from "@/components/JobDetailParts";
import { ChevronRightIcon } from "@/components/Icons";
import { MatchPanel } from "@/components/Match";
import { ReportDialog } from "@/components/ReportDialog";
import { type JobDetail, api } from "@/lib/api";
import { TECH_ROLES } from "@/lib/filters";
import { possessive, shortLocation } from "@/lib/format";

type Props = { params: Promise<{ id: string }> };

// metadata and the page both need the job: cache() makes that one API call per request
const getJob = cache((id: number) => api.job(id));

async function load(params: Props["params"]): Promise<JobDetail> {
  const { id } = await params;
  const jobId = Number(id);
  if (!Number.isSafeInteger(jobId) || jobId < 1) notFound();
  const job = await getJob(jobId);
  if (!job) notFound();
  return job;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const job = await load(params);
  return {
    title: `${job.title} at ${job.company}`,
    description: `${job.title} at ${job.company}, ${shortLocation(job.location)}: true posting age, repost history and ghost job signals.`,
    alternates: { canonical: `/jobs/${job.id}` },
  };
}

export default async function JobPage({ params }: Props) {
  const job = await load(params);
  const more = await api.jobs({
    company: [job.company],
    role: job.role_type === "other" ? undefined : [...TECH_ROLES],
    limit: 4,
  });
  const others = more.items.filter((j) => j.id !== job.id).slice(0, 3);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <nav aria-label="Breadcrumb" className="mb-6">
        <ol className="flex flex-wrap items-center gap-1 text-sm text-ink-soft">
          <li>
            <Link href="/jobs" className="hover:text-accent hover:underline">
              Jobs
            </Link>
          </li>
          <li aria-hidden="true">
            <ChevronRightIcon className="size-3.5 text-ink-faint" />
          </li>
          <li>
            <Link href={`/companies/${job.company_slug}`} className="hover:text-accent hover:underline">
              {job.company}
            </Link>
          </li>
        </ol>
      </nav>

      <div className="mb-8 border-b border-line pb-8">
        <JobHeader job={job} />
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-12">
        {/* the record first: it's what Ghostless adds; the personal match follows */}
        <aside className="space-y-4 lg:order-2" aria-label="Posting record and disclosures">
          <PostingRecord job={job} />
          <MatchPanel jobId={job.id} hasDescription={Boolean(job.description)} />
          <PostingHistory job={job} />
          <Disclosures job={job} />
          <p className="px-1 text-sm text-ink-soft">
            Something wrong with this posting? <ReportDialog jobId={job.id} label="Report it" className="link" />
          </p>
        </aside>

        <article className="min-w-0 space-y-8 lg:order-1">
          <SkillChips skills={job.skills} />
          <JobDescription job={job} />
          {others.length > 0 && (
            <section className="border-t border-line pt-8">
              <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-xl font-semibold text-ink">More open roles at {job.company}</h2>
                <Link href={`/companies/${job.company_slug}`} className="link text-sm">
                  See {possessive(job.company)} hiring record
                </Link>
              </div>
              <JobList jobs={others} headingLevel="h3" />
            </section>
          )}
        </article>
      </div>
    </div>
  );
}
