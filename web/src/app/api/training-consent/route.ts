import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, signedIn, visitorClient } from "@/lib/route";

/* Whether a signed-in person's feedback may be used to improve matching. Off unless they turn it on. */

export async function GET() {
  if (!(await signedIn())) return NextResponse.json({ detail: "Sign in first." }, { status: 401 });
  return respond(async () => api.trainingConsent(await visitorClient()));
}

/** { given: boolean } */
export async function PUT(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  if (typeof body?.given !== "boolean") return badRequest();
  return respond(async () => api.setTrainingConsent(await visitorClient(), body.given as boolean));
}
