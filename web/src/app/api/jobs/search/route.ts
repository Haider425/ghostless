import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { respond } from "@/lib/route";

/** A few open jobs by title, for pickers (the builder's "Tailor to a job"). */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim().slice(0, 100) ?? "";
  if (q.length < 2) return NextResponse.json([]);
  return respond(async () => {
    const page = await api.jobs({ q, limit: 8 });
    return page.items.map((j) => ({ id: j.id, title: j.title, company: j.company, location: j.location }));
  });
}
