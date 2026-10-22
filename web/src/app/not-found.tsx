import Link from "next/link";

import { GhostMascot } from "@/components/GhostMascot";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center sm:px-6">
      <GhostMascot className="mx-auto mb-5 w-24" />
      <h1 className="page-title">There&apos;s nothing at this address</h1>
      <p className="page-lead">
        The posting may have been removed, or the link is mistyped. Postings Ghostless has seen are never deleted, so
        an old link to a real job still works.
      </p>
      <Link
        href="/jobs"
        className="btn btn-primary mt-6"
      >
        Search jobs
      </Link>
    </div>
  );
}
