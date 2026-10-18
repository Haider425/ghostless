import "server-only";

/*
  Shared pieces of the Google and GitHub sign-in routes. The flow:

  1. /api/auth/oauth/<provider>/start makes a random `state` and a PKCE code
     verifier, keeps them in a short-lived httpOnly cookie, and redirects to
     the provider.
  2. The provider sends the visitor back to /api/auth/oauth/<provider>/callback
     with a code. The state must match the cookie (so another site can't
     complete a sign-in into your browser), and the code plus the verifier go
     to the API, which holds the client secret and finishes the sign-in.
*/

export const PROVIDERS = ["google", "github"] as const;
export type Provider = (typeof PROVIDERS)[number];
export const OAUTH_COOKIE = "gl_oauth";
export const OAUTH_COOKIE_PATH = "/api/auth/oauth";

export interface PendingSignIn {
  provider: Provider;
  state: string;
  verifier: string;
  next: string;
  link: boolean; // adding a sign-in method to the current account
}

export function isProvider(value: string): value is Provider {
  return (PROVIDERS as readonly string[]).includes(value);
}

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000").replace(/\/+$/, "");
}

export function callbackUrl(provider: Provider): string {
  return `${siteUrl()}/api/auth/oauth/${provider}/callback`;
}

/** An absolute URL on this site, for redirects. */
export function sitePath(path: string): string {
  return `${siteUrl()}${path}`;
}

function base64url(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(bytes = 32): string {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

/** The PKCE challenge for a verifier: base64url(SHA-256(verifier)). */
export async function codeChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

/** Compare secrets without leaking how much matched through timing. */
export function sameSecret(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Fixed messages for sign-in problems, shown by code so links can't inject text. */
export const OAUTH_ERRORS = {
  oauth_cancelled: "Sign-in was cancelled.",
  oauth_expired: "That sign-in took too long or was started in another tab. Please try again.",
  oauth_unverified: "That account's email address isn't verified with the provider yet. Verify it there, then try again.",
  oauth_in_use: "That Google or GitHub account is already linked to a different Ghostless account.",
  oauth_unavailable: "That sign-in option isn't available right now.",
  oauth_failed: "The sign-in didn't go through. Please try again.",
} as const;
export type OAuthErrorCode = keyof typeof OAUTH_ERRORS;

export function oauthErrorMessage(code: string | undefined): string | null {
  return code && code in OAUTH_ERRORS ? OAUTH_ERRORS[code as OAuthErrorCode] : null;
}
