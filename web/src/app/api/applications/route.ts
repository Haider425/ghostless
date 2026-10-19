import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, signedIn, visitorClient } from "@/lib/route";

/*
  "Yes, I applied" for ?id=. Saves the job if it isn't saved and marks it
  applied; safe to repeat. Ghostless records what the person tells it: it
  can't see whether an application reached the employer.
*/

export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  if (!(await signedIn())) return NextResponse.json({ detail: "Sign in to track applications." }, { status: 401 });
  const id = Number(new URL(request.url).searchParams.get("id"));
  if (!Number.isSafeInteger(id) || id < 1) return badRequest();
  const body = await jsonBody(request);
  const source = body?.source === "tracker" ? "tracker" : "apply_prompt";
  return respond(async () => api.recordApplication(await visitorClient(), id, source));
}
