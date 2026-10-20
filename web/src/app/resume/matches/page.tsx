import type { Metadata } from "next";

import { Matches } from "./Matches";

export const metadata: Metadata = {
  title: "Jobs that fit your resume",
  description: "Open tech jobs ranked by how well your resume matches, leaving out likely ghost jobs.",
  robots: { index: false },
};

export default function MatchesPage() {
  return (
    <div className="mx-auto max-w-[80rem] px-4 pt-10 pb-20 sm:px-6 lg:px-20">
      <h1 className="page-title">Jobs that fit you</h1>
      <p className="page-lead">
        Every open tech job, ranked by how well your resume matches. Likely ghost jobs are left out unless you ask for them.
      </p>
      <Matches />
    </div>
  );
}
