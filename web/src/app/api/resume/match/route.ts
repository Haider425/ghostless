import type { Profile } from "@/lib/api";
import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

/** Match scores for up to 100 jobs, from a profile kept in the browser or a saved resume. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  const ids = Array.isArray(body?.job_ids) ? body.job_ids.filter((n): n is number => Number.isSafeInteger(n)).slice(0, 100) : [];
  const resumeId = Number(body?.resume_id);
  const profile = body?.profile && typeof body.profile === "object" ? (body.profile as Profile) : null;
  if (!ids.length || (!profile && !Number.isSafeInteger(resumeId))) return badRequest();
  return respond(async () =>
    api.match(await visitorClient(), {
      job_ids: ids,
      ...(Number.isSafeInteger(resumeId) ? { resume_id: resumeId } : { profile }),
    }),
  );
}
