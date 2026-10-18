import "server-only";

import { cookies } from "next/headers";

import { type User, api, attempt, authedClient } from "./api";
import { PREFS_COOKIE, PREFS_MAX_AGE, parsePrefsCookie, serializePrefs } from "./prefs";
import { setSessionCookie, visitorHeaders } from "./session";

/*
  What happens after any successful sign-in (password, Google or GitHub):
  the session cookie is set, and the account's display settings win over
  this browser's, unless the account still has the defaults, in which case
  this browser's settings are carried over to it.
*/

export async function finishSignIn(user: User, token: string): Promise<void> {
  await setSessionCookie(token);
  const store = await cookies();
  const local = parsePrefsCookie(store.get(PREFS_COOKIE)?.value);
  const fromAccount = user.settings;
  const accountIsDefault = JSON.stringify(fromAccount) === JSON.stringify(parsePrefsCookie(undefined));
  const prefs = accountIsDefault ? local : fromAccount;
  store.set(PREFS_COOKIE, serializePrefs(prefs as typeof local), {
    path: "/",
    maxAge: PREFS_MAX_AGE,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  if (accountIsDefault && JSON.stringify(local) !== JSON.stringify(fromAccount)) {
    await attempt(api.saveSettings(authedClient(token, await visitorHeaders()), local));
  }
}

/** Only redirect back to pages on this site. */
export function safeNext(value: string | null | undefined): string {
  const next = value ?? "";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}
