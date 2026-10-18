import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  const text = typeof body?.text === "string" ? body.text : "";
  if (text.trim().length < 50) return badRequest("Add more to your resume first: it's under 50 characters.");
  return respond(async () => api.analyzeText(await visitorClient(), text.slice(0, 60_000)));
}
