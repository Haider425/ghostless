import { api } from "@/lib/api";
import { badRequest, jsonBody, respond, sameOrigin, visitorClient } from "@/lib/route";

type Ctx = { params: Promise<{ id: string }> };

async function idOf(ctx: Ctx) {
  const id = Number((await ctx.params).id);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export async function GET(_: Request, ctx: Ctx) {
  const id = await idOf(ctx);
  if (!id) return badRequest();
  return respond(async () => api.resume(await visitorClient(), id));
}

/** Update a builder resume. */
export async function PUT(request: Request, ctx: Ctx) {
  const id = await idOf(ctx);
  const body = await jsonBody(request);
  if (!id || !sameOrigin(request) || !body?.document) return badRequest();
  return respond(async () =>
    api.updateResume(await visitorClient(), id, { title: String(body.title ?? "My resume").slice(0, 80), document: body.document as never }),
  );
}

export async function DELETE(request: Request, ctx: Ctx) {
  const id = await idOf(ctx);
  if (!id || !sameOrigin(request)) return badRequest();
  return respond(async () => api.deleteResume(await visitorClient(), id));
}
