import type { Metadata } from "next";

import { api } from "@/lib/api";
import { normalizeDoc } from "@/lib/resumeDoc";
import { visitorClient } from "@/lib/route";
import { currentUser } from "@/lib/session";

import { BuilderClient } from "./BuilderClient";

export const metadata: Metadata = {
  title: "Resume builder",
  description: "Build a clean, one-column resume that applicant tracking systems can read, with tips on every bullet. Free.",
};

export default async function BuilderPage({ searchParams }: { searchParams: Promise<{ id?: string; new?: string; from?: string; job?: string }> }) {
  const { id, new: fresh, job } = await searchParams;
  let { from } = await searchParams;
  const user = await currentUser();
  let initial = null;
  let title = "My resume";
  let resumeId: number | null = null;
  if (user && id && Number.isSafeInteger(Number(id))) {
    const stored = await api.resume(await visitorClient(), Number(id)).catch(() => null);
    if (stored?.kind === "built" && stored.document) {
      initial = normalizeDoc(stored.document);
      title = stored.title;
      resumeId = stored.id;
    } else if (stored) {
      from = id; // an upload: open a builder copy of it
    }
  }
  // an uploaded resume, read into the builder as a new copy
  let imported = false;
  if (user && !initial && from && Number.isSafeInteger(Number(from))) {
    const client = await visitorClient();
    const [stored, document] = await Promise.all([
      api.resume(client, Number(from)).catch(() => null),
      api.resumeAsDocument(client, Number(from)).catch(() => null),
    ]);
    if (stored && document) {
      initial = normalizeDoc(document);
      title = `${stored.title} (builder copy)`.slice(0, 80);
      imported = true;
    }
  }
  const tailorJob = job && Number.isSafeInteger(Number(job)) ? await api.job(Number(job)).catch(() => null) : null;
  return (
    <div className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
      <h1 className="sr-only">Resume builder</h1>
      <BuilderClient
        key={resumeId ?? (imported ? `from-${from}` : fresh ? "new" : "draft")}
        initial={initial}
        resumeId={resumeId}
        initialTitle={title}
        startEmpty={Boolean(fresh)}
        imported={imported}
        tailorTo={tailorJob ? { id: tailorJob.id, title: tailorJob.title, company: tailorJob.company } : null}
      />
    </div>
  );
}
