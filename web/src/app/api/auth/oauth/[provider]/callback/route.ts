import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { api, attempt, authedClient } from "@/lib/api";
import {
  OAUTH_COOKIE,
  OAUTH_COOKIE_PATH,
  type OAuthErrorCode,
  type PendingSignIn,
  callbackUrl,
  isProvider,
  sameSecret,
  sitePath,
} from "@/lib/oauth";
import { sessionToken, visitorHeaders } from "@/lib/session";
import { finishSignIn } from "@/lib/signin";

function readPending(raw: string | undefined): PendingSignIn | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingSignIn>;
    if (typeof value.state !== "string" || typeof value.verifier !== "string" || typeof value.provider !== "string") return null;
    return { ...value, next: typeof value.next === "string" ? value.next : "/", link: Boolean(value.link) } as PendingSignIn;
  } catch {
    return null;
  }
}

/** The provider sends the visitor back here with a code (or an error). */
export async function GET(request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  const url = new URL(request.url);
  const store = await cookies();
  const pending = readPending(store.get(OAUTH_COOKIE)?.value);
  store.delete({ name: OAUTH_COOKIE, path: OAUTH_COOKIE_PATH }); // one use only

  const fail = (code: OAuthErrorCode) =>
    NextResponse.redirect(sitePath(`${pending?.link ? "/account" : "/login"}?error=${code}`));

  if (url.searchParams.get("error")) return fail("oauth_cancelled"); // the visitor said no at the provider
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state") ?? "";
  if (!isProvider(provider) || !pending || pending.provider !== provider || !code || !sameSecret(state, pending.state)) {
    return fail("oauth_expired");
  }

  // linking sends the current session, so the API adds the provider to this account
  const token = pending.link ? await sessionToken() : undefined;
  const result = await attempt(
    api.oauthFinish(authedClient(token, await visitorHeaders()), provider, {
      code,
      redirect_uri: callbackUrl(provider),
      code_verifier: pending.verifier,
    }),
  );
  if (!result.ok) {
    if (result.status === 409) return fail("oauth_in_use");
    if (result.status === 400 && /verified/i.test(result.message)) return fail("oauth_unverified");
    if (result.status === 404) return fail("oauth_unavailable");
    return fail("oauth_failed");
  }

  if (pending.link) return NextResponse.redirect(sitePath(`/account?linked=${provider}`));
  await finishSignIn(result.data.user, result.data.token);
  // a brand new account gets the same welcome as an email sign-up
  const isNew = Date.now() - new Date(result.data.user.created_at).getTime() < 2 * 60_000;
  return NextResponse.redirect(sitePath(isNew && pending.next === "/" ? "/account?welcome=1" : pending.next));
}
