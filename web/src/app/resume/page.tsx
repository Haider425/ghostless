import type { Metadata } from "next";

import { api } from "@/lib/api";
import { visitorClient } from "@/lib/route";
import { currentUser } from "@/lib/session";

import { ResumeHub } from "./ResumeHub";

export const metadata: Metadata = {
  title: "Resume check and job matches",
  description:
    "Upload your resume to see how strong it is, what to fix, and how well you match every open tech job. Free, no AI required.",
};

export default async function ResumePage() {
  const user = await currentUser();
  const resumes = user ? await api.resumes(await visitorClient()).catch(() => []) : [];
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="mb-6 max-w-2xl">
        <h1 className="text-3xl font-semibold text-ink">Your resume</h1>
        <p className="mt-2 text-ink-soft">
          See how strong it is, what to fix first, and how well you match every open tech job on Ghostless.
        </p>
      </div>
      <ResumeHub signedIn={Boolean(user)} resumes={resumes} />
    </div>
  );
}
