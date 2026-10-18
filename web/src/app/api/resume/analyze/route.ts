import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api";
import { badRequest, sameOrigin } from "@/lib/route";
import { sessionToken, visitorHeaders } from "@/lib/session";

/** Upload a resume file for analysis. The file passes through; it isn't stored here. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  if (!(file instanceof File)) return badRequest("Choose a PDF or Word file.");
  if (file.size > 5 * 1024 * 1024) return NextResponse.json({ detail: "Resumes can be up to 5 MB." }, { status: 413 });

  const token = await sessionToken();
  const save = Boolean(token) && new URL(request.url).searchParams.get("save") === "1";
  const upstream = new FormData();
  upstream.append("file", file, file.name);
  let response: Response;
  try {
    response = await fetch(`${API_URL}/resume/analyze?save=${save}`, {
      method: "POST",
      body: upstream,
      headers: { ...(await visitorHeaders()), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "The analysis service isn't reachable right now. Try again shortly." }, { status: 502 });
  }
  const data: unknown = await response.json().catch(() => ({ detail: "The analysis failed." }));
  return NextResponse.json(data, { status: response.status, headers: { "Cache-Control": "private, no-store" } });
}
