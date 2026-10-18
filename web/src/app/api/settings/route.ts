import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { PREFS_COOKIE, PREFS_MAX_AGE, cleanPrefs, serializePrefs } from "@/lib/prefs";
import { badRequest, jsonBody, sameOrigin, signedIn, visitorClient } from "@/lib/route";

/** Save display preferences: in a cookie for everyone, and on the account when signed in. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return badRequest();
  const body = await jsonBody(request);
  if (!body) return badRequest();
  const prefs = cleanPrefs(body);
  (await cookies()).set(PREFS_COOKIE, serializePrefs(prefs), {
    path: "/",
    maxAge: PREFS_MAX_AGE,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  let synced = false;
  if (await signedIn()) {
    synced = await api.saveSettings(await visitorClient(), prefs).then(
      () => true,
      () => false,
    );
  }
  return NextResponse.json({ prefs, synced });
}
