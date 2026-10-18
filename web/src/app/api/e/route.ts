import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { jsonBody, visitorClient } from "@/lib/route";

/** Page views and client errors, forwarded to the API. Always answers 204. */
export async function POST(request: Request) {
  const body = await jsonBody(request);
  if (body && (body.kind === "pageview" || body.kind === "error")) {
    const str = (v: unknown, max: number) => (typeof v === "string" ? v.slice(0, max) : null);
    await api.event(await visitorClient(), {
      kind: body.kind,
      path: str(body.path, 500),
      referrer: str(body.referrer, 500),
      message: str(body.message, 1000),
      digest: str(body.digest, 100),
    });
  }
  return new NextResponse(null, { status: 204 });
}
