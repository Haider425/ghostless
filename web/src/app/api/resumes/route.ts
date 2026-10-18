import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

/** Save a new builder resume to the account. */
export async function POST(request: Request) {
  const body = await jsonBody(request);
  if (!sameOrigin(request) || !body?.document) return badRequest();
  return respond(
    async () =>
      api.createResume(await visitorClient(), { title: String(body.title ?? "My resume").slice(0, 80), document: body.document as never }),
    201,
  );
}
