"use client";

import Link from "next/link";

import { useActiveResume } from "@/lib/resume";

import { ChevronRightIcon, DocIcon } from "./Icons";

/** On the jobs list: the way into "Jobs that fit you", or to adding a resume first. */
export function MatchesLink() {
  const { resume, ready } = useActiveResume();
  if (!ready) return null;
  return (
    <Link
      href={resume ? "/resume/matches" : "/resume"}
      className="inline-flex h-8 items-center gap-1.5 rounded-full bg-accent-tint pr-2.5 pl-3 text-sm font-semibold text-accent hover:underline"
    >
      <DocIcon className="size-4" />
      {resume ? "Jobs that fit your resume" : "Match your resume"}
      <ChevronRightIcon className="size-3.5" />
    </Link>
  );
}
