import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, signedIn, visitorClient } from "@/lib/route";

/** Move a resume checked before signing in into the account. */
export async function POST(request: Request) {
  const body = await jsonBody(request);
  if (!sameOrigin(request) || !body?.analysis || !(await signedIn())) return badRequest();
  return respond(
    async () =>
      api.importResume(await visitorClient(), {
        title: String(body.title ?? "My resume").slice(0, 80) || "My resume",
        analysis: body.analysis as never,
      }),
    201,
  );
}
