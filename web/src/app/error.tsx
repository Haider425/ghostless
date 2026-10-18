"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center sm:px-6">
      <h1 className="text-4xl font-semibold text-ink">This page couldn&apos;t load</h1>
      <p className="mt-3 text-ink-soft">
        Ghostless couldn&apos;t reach its job data. This is usually brief. Try again in a moment.
      </p>
      {error.digest && <p className="mt-2 text-xs text-ink-faint">Reference: {error.digest}</p>}
      <div className="mt-6 flex justify-center gap-3">
        <button
          type="button"
          onClick={reset}
          className="h-10 rounded-lg bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover"
        >
          Try again
        </button>
        <Link href="/" className="inline-flex h-10 items-center rounded-md border border-line-strong px-4 font-medium text-ink hover:border-accent">
          Go to the home page
        </Link>
      </div>
    </div>
  );
}
