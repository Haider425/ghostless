import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { signedIn, visitorClient } from "@/lib/route";

/** The signed-in visitor's primary resume, used for match scores. */
export async function GET() {
  if (!(await signedIn())) return NextResponse.json(null);
  const client = await visitorClient();
  const resumes = await api.resumes(client).catch(() => []);
  const primary = resumes.find((r) => r.is_primary) ?? resumes[0];
  if (!primary) return NextResponse.json(null, { headers: { "Cache-Control": "private, no-store" } });
  const full = await api.resume(client, primary.id);
  return NextResponse.json(
    full?.analysis ? { id: full.id, title: full.title, analysis: full.analysis, updated_at: full.updated_at } : null,
    { headers: { "Cache-Control": "private, no-store" } },
  );
}
