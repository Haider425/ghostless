import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { api, attempt, authedClient } from "@/lib/api";
import {
  OAUTH_COOKIE,
  OAUTH_COOKIE_PATH,
  type PendingSignIn,
  callbackUrl,
  codeChallenge,
  isProvider,
  randomToken,
  sitePath,
} from "@/lib/oauth";
import { sessionToken } from "@/lib/session";
import { safeNext } from "@/lib/signin";

/** Send the visitor to Google or GitHub. ?next= is where to land afterwards; ?link=1 adds the provider to the current account. */
export async function GET(request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  const url = new URL(request.url);
  const link = url.searchParams.get("link") === "1" && Boolean(await sessionToken());
  const back = link ? "/account" : "/login";
  if (!isProvider(provider)) return NextResponse.redirect(sitePath(`${back}?error=oauth_unavailable`));

  const pending: PendingSignIn = {
    provider,
    state: randomToken(),
    verifier: randomToken(48), // 64 characters, within PKCE's 43 to 128
    next: safeNext(url.searchParams.get("next")),
    link,
  };
  const result = await attempt(
    api.oauthAuthorize(authedClient(undefined, {}), provider, {
      redirect_uri: callbackUrl(provider),
      state: pending.state,
      code_challenge: await codeChallenge(pending.verifier),
    }),
  );
  if (!result.ok) return NextResponse.redirect(sitePath(`${back}?error=oauth_unavailable`));

  (await cookies()).set(OAUTH_COOKIE, JSON.stringify(pending), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax", // sent when the provider redirects back (a top-level GET)
    path: OAUTH_COOKIE_PATH,
    maxAge: 600,
  });
  return NextResponse.redirect(result.data.url);
}
