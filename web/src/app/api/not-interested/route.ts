import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, signedIn, visitorClient } from "@/lib/route";

/* "Not interested" on a match, for signed-in visitors. Signed-out visitors hide matches in the browser only. */

const REASONS = ["level", "location", "role", "company"] as const;

export async function GET() {
  if (!(await signedIn())) return NextResponse.json({ detail: "Sign in to keep this feedback." }, { status: 401 });
  return respond(async () => api.notInterestedIds(await visitorClient()));
}

/** { reason?, resume_id? } for ?id= */
export async function PUT(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const id = Number(new URL(request.url).searchParams.get("id"));
  const body = await jsonBody(request);
  if (!Number.isSafeInteger(id) || !body) return badRequest();
  const reason = REASONS.find((r) => r === body.reason) ?? null;
  const resume_id = Number.isSafeInteger(body.resume_id) ? (body.resume_id as number) : null;
  return respond(async () => api.notInterested(await visitorClient(), id, { reason, resume_id }));
}

export async function DELETE(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const id = Number(new URL(request.url).searchParams.get("id"));
  if (!Number.isSafeInteger(id)) return badRequest();
  return respond(async () => api.undoNotInterested(await visitorClient(), id));
}
