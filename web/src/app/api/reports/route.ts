import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

const CATEGORIES = ["wrong_job_info", "broken_link", "site_bug", "suggestion", "other"] as const;

export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  const category = CATEGORIES.find((c) => c === body?.category);
  const message = typeof body?.message === "string" ? body.message.trim() : "";
  if (!category || message.length < 3) return badRequest("Tell us a little about the problem.");
  const jobId = Number(body?.job_id);
  return respond(
    async () =>
      api.report(await visitorClient(), {
        category,
        message: message.slice(0, 4000),
        page: typeof body?.page === "string" ? body.page.slice(0, 500) : null,
        job_id: Number.isSafeInteger(jobId) && jobId > 0 ? jobId : null,
        email: typeof body?.email === "string" && body.email.trim() ? body.email.trim().slice(0, 254) : null,
      }),
    201,
  );
}
