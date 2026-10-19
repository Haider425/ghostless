import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, signedIn, visitorClient } from "@/lib/route";

/* Saved jobs for signed-in visitors. Signed-out visitors keep theirs in the browser. */

export async function GET() {
  if (!(await signedIn())) return NextResponse.json({ detail: "Sign in to sync saved jobs." }, { status: 401 });
  return respond(async () => api.savedIds(await visitorClient()));
}

const STATUSES = ["saved", "applied", "interviewing", "offer", "rejected"] as const;

/** A date the person picked ("2026-09-02"), as noon UTC so it shows as that day everywhere; null clears it. */
function appliedAt(value: unknown): string | null | undefined {
  if (value === null) return null;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime()) || date.getTime() > Date.now() + 86_400_000 ? undefined : date.toISOString();
}

/** Update an application: { status?, notes?, applied_at? } for ?id= */
export async function PATCH(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const id = Number(new URL(request.url).searchParams.get("id"));
  const body = await jsonBody(request);
  if (!Number.isSafeInteger(id) || !body) return badRequest();
  const status = STATUSES.find((s) => s === body.status);
  const notes = typeof body.notes === "string" ? body.notes.slice(0, 2000) : undefined;
  const applied = "applied_at" in body ? appliedAt(body.applied_at) : undefined;
  if ("applied_at" in body && applied === undefined) return badRequest(); // not a date, or in the future
  if (!status && notes === undefined && applied === undefined) return badRequest();
  return respond(async () =>
    api.updateSaved(await visitorClient(), id, { status, notes, ...(applied !== undefined && { applied_at: applied }) }),
  );
}

export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  const ids = Array.isArray(body?.job_ids) ? body.job_ids.filter((n): n is number => Number.isSafeInteger(n)) : null;
  if (!ids) return badRequest();
  return respond(async () => api.saveJobs(await visitorClient(), ids.slice(0, 500)));
}

export async function DELETE(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const id = Number(new URL(request.url).searchParams.get("id"));
  if (!Number.isSafeInteger(id)) return badRequest();
  return respond(async () => api.unsaveJob(await visitorClient(), id));
}
