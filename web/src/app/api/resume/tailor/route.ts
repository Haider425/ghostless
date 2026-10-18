import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

/** Score a builder draft against one job, as the person edits. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  const text = typeof body?.text === "string" ? body.text.slice(0, 60_000) : "";
  const jobId = Number(body?.job_id);
  if (!text.trim() || !Number.isSafeInteger(jobId)) return badRequest("Choose a job to tailor to.");
  return respond(async () => api.tailor(await visitorClient(), { text, job_id: jobId }));
}
