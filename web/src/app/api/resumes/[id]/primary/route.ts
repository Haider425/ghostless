import { api } from "@/lib/api";
import { badRequest, respond, sameOrigin, visitorClient } from "@/lib/route";

export async function POST(request: Request, ctx: { params: Promise<{ id: string }> }) {
  const id = Number((await ctx.params).id);
  if (!Number.isSafeInteger(id) || !sameOrigin(request)) return badRequest();
  return respond(async () => api.primaryResume(await visitorClient(), id));
}
