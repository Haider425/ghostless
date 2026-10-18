import Link from "next/link";

import { GhostMark } from "@/components/Logo";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center sm:px-6">
      <GhostMark className="mx-auto mb-4 size-10 text-accent" />
      <h1 className="text-4xl font-semibold text-ink">There&apos;s nothing at this address</h1>
      <p className="mt-3 text-ink-soft">
        The posting may have been removed, or the link is mistyped. Postings Ghostless has seen are never deleted, so
        an old link to a real job still works.
      </p>
      <Link
        href="/jobs"
        className="mt-6 inline-flex h-10 items-center rounded-lg bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover"
      >
        Search jobs
      </Link>
    </div>
  );
}
