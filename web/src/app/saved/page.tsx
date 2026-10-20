import type { Metadata } from "next";
import Link from "next/link";

import { api } from "@/lib/api";
import { visitorClient } from "@/lib/route";
import { currentUser } from "@/lib/session";

import { SavedList } from "./SavedList";
import { Tracker } from "./Tracker";

export const metadata: Metadata = {
  title: "Saved jobs",
  robots: { index: false },
};

export default async function SavedPage() {
  const user = await currentUser();
  const entries = user ? await api.savedJobs(await visitorClient()).catch(() => null) : null;

  return (
    <div className="mx-auto max-w-5xl px-4 pt-10 pb-20 sm:px-6">
      <div className="mb-6 space-y-2">
        <h1 className="page-title">{user ? "Applications" : "Saved jobs"}</h1>
        {user ? (
          <p className="page-lead">
            Every job you&apos;ve saved, and where each application stands. Notes are private to you.
          </p>
        ) : (
          <p className="text-ink-soft">
            Saved in this browser only.{" "}
            <Link href="/signup?next=/saved" className="link">
              Create a free account
            </Link>{" "}
            to keep them on every device and track each application.
          </p>
        )}
      </div>
      {user ? <Tracker initial={entries ?? []} failed={entries === null} /> : <SavedList />}
    </div>
  );
}
