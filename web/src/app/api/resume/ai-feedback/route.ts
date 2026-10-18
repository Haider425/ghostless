import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, signedIn, visitorClient } from "@/lib/route";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  if (!(await signedIn())) return NextResponse.json({ detail: "Sign in to get AI feedback." }, { status: 401 });
  const body = await jsonBody(request);
  const jobId = Number(body?.job_id);
  const resumeId = Number(body?.resume_id);
  const text = typeof body?.text === "string" ? body.text.slice(0, 60_000) : null;
  if (!Number.isSafeInteger(jobId)) return badRequest();
  return respond(async () =>
    api.aiFeedback(await visitorClient(), {
      job_id: jobId,
      ...(Number.isSafeInteger(resumeId) ? { resume_id: resumeId } : { text }),
    }),
  );
}
