import "server-only";

import { cookies, headers } from "next/headers";
import { cache } from "react";

import { type User, api, authedClient } from "./api";
import { PREFS_COOKIE, type Prefs, parsePrefsCookie } from "./prefs";

/*
  Sessions. The API issues a token at sign-in; the website keeps it in an
  httpOnly cookie, so page scripts can never read it, and sends it to the API
  from the server on the visitor's behalf.
*/

export const SESSION_COOKIE = "gl_session";
export const SESSION_MAX_AGE = 60 * 60 * 24 * 30;

export async function sessionToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

/** Who is visiting, from their request: forwarded to the API for rate limits and analytics. */
export async function visitorHeaders(): Promise<Record<string, string>> {
  const h = await headers();
  const ip = h.get("x-forwarded-for")?.split(",")[0]?.trim() || h.get("x-real-ip") || "";
  const out: Record<string, string> = {};
  if (process.env.GHOSTLESS_INTERNAL_KEY && ip) {
    out["x-internal-key"] = process.env.GHOSTLESS_INTERNAL_KEY;
    out["x-client-ip"] = ip;
  }
  const ua = h.get("user-agent");
  if (ua) out["x-client-user-agent"] = ua.slice(0, 300);
  return out;
}

/** The signed-in user, or null. One API call per request at most. */
export const currentUser = cache(async (): Promise<User | null> => {
  const token = await sessionToken();
  if (!token) return null;
  return api.me(authedClient(token, await visitorHeaders()));
});

export const currentPrefs = cache(async (): Promise<Prefs> => {
  const user = await currentUser();
  if (user) return user.settings as Prefs;
  return parsePrefsCookie((await cookies()).get(PREFS_COOKIE)?.value);
});

export async function setSessionCookie(token: string): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
}

export async function clearSessionCookie(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
