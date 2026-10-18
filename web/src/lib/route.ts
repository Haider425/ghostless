import "server-only";

import { NextResponse } from "next/server";

import { ApiError, authedClient } from "./api";
import { sessionToken, visitorHeaders } from "./session";

/* Helpers for the website's own /api routes, which call the Ghostless API for the visitor. */

export async function visitorClient() {
  return authedClient(await sessionToken(), await visitorHeaders());
}

export async function signedIn(): Promise<boolean> {
  return Boolean(await sessionToken());
}

/** Run an API call and turn its result or error into a JSON response. */
export async function respond<T>(work: () => Promise<T>, status = 200): Promise<NextResponse> {
  try {
    const data = await work();
    return NextResponse.json(data ?? null, { status, headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status || 502 });
    }
    throw error;
  }
}

/** Read a JSON body, or null if it isn't valid JSON. */
export async function jsonBody(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const body: unknown = await request.json();
    return body && typeof body === "object" ? (body as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export function badRequest(detail = "That request wasn't understood.") {
  return NextResponse.json({ detail }, { status: 400 });
}

/**
 * Only pages on this site may call these routes (a second line of defence next
 * to SameSite cookies). The browser's Origin is compared with the host it
 * addressed (behind a proxy, X-Forwarded-Host), not with request.url, which
 * can name a different host than the one in the address bar.
 */
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true; // same-origin GETs and beacons may omit it
  let host: string;
  try {
    host = new URL(origin).host;
  } catch {
    return false;
  }
  const addressed = (request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? "").split(",")[0]?.trim();
  const site = process.env.NEXT_PUBLIC_SITE_URL ? new URL(process.env.NEXT_PUBLIC_SITE_URL).host : null;
  return host === addressed || host === site;
}
