import type { Metadata } from "next";

import { Matches } from "./Matches";

export const metadata: Metadata = {
  title: "Jobs that fit your resume",
  description: "Open tech jobs ranked by how well your resume matches, leaving out likely ghost jobs.",
  robots: { index: false },
};

export default function MatchesPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <h1 className="text-4xl font-semibold text-ink">Jobs that fit you</h1>
      <p className="mt-2 text-lg text-ink-soft">
        Every open tech job, ranked by how well your resume matches. Likely ghost jobs are left out unless you ask for them.
      </p>
      <Matches />
    </div>
  );
}
