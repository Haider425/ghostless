import type { Profile } from "@/lib/api";
import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

const LOCATIONS = ["any", "canada", "remote", "canada_or_remote"] as const;

export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  const resumeId = Number(body?.resume_id);
  const profile = body?.profile && typeof body.profile === "object" ? (body.profile as Profile) : null;
  if (!profile && !Number.isSafeInteger(resumeId)) return badRequest();
  const location = LOCATIONS.find((l) => l === body?.location) ?? "any";
  const offset = Math.max(0, Math.min(1000, Math.trunc(Number(body?.offset) || 0)));
  return respond(async () =>
    api.recommendations(await visitorClient(), {
      ...(Number.isSafeInteger(resumeId) ? { resume_id: resumeId } : { profile }),
      location,
      include_high_risk: body?.include_high_risk === true,
      limit: 30,
      offset,
    }),
  );
}
