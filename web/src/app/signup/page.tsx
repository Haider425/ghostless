import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { OAuthButtons } from "@/components/OAuthButtons";
import { api } from "@/lib/api";
import { oauthErrorMessage } from "@/lib/oauth";
import { currentUser } from "@/lib/session";
import { safeNext } from "@/lib/signin";

import { SignupForm } from "./SignupForm";

export const metadata: Metadata = {
  title: "Create an account",
  description: "A free Ghostless account syncs your saved jobs, resumes and settings across devices.",
};

export default async function SignupPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const params = await searchParams;
  if (await currentUser()) redirect("/account");
  const next = safeNext(params.next);
  const providers = await api.providers();
  return (
    <SignupForm
      next={next}
      notice={oauthErrorMessage(params.error)}
      oauth={
        <OAuthButtons
          enabled={providers}
          next={next}
          note={
            <>
              By continuing with Google or GitHub, you agree to the{" "}
              <Link href="/terms" className="underline hover:text-ink">terms</Link> and{" "}
              <Link href="/privacy" className="underline hover:text-ink">privacy policy</Link>.
            </>
          }
        />
      }
    />
  );
}
