import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { OAuthButtons } from "@/components/OAuthButtons";
import { api } from "@/lib/api";
import { oauthErrorMessage } from "@/lib/oauth";
import { currentUser } from "@/lib/session";
import { safeNext } from "@/lib/signin";

import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in", robots: { index: false } };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const params = await searchParams;
  const next = safeNext(params.next);
  if (await currentUser()) redirect(next === "/" ? "/account" : next);
  const providers = await api.providers();
  return (
    <LoginForm
      next={next}
      notice={oauthErrorMessage(params.error)}
      oauth={<OAuthButtons enabled={providers} next={next} />}
    />
  );
}

