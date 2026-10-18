"use client";

import Link from "next/link";
import { type ReactNode, useActionState } from "react";

import { type FormState, signIn } from "@/app/actions/auth";
import { AuthCard, Field, FormMessage, SubmitButton } from "@/components/Form";

export function LoginForm({ next, oauth, notice }: { next: string; oauth?: ReactNode; notice?: string | null }) {
  const [state, action] = useActionState<FormState, FormData>(signIn, {});
  return (
    <AuthCard
      title="Sign in"
      lead="Your saved jobs, resumes and settings, on every device."
      footer={
        <>
          New to Ghostless?{" "}
          <Link href={`/signup${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} className="link">
            Create a free account
          </Link>
        </>
      }
    >
      {notice && (
        <p role="alert" className="mb-4 rounded-lg bg-brick-tint px-3 py-2.5 text-sm text-brick">
          {notice}
        </p>
      )}
      {oauth && <div className="mb-5">{oauth}</div>}
      <form action={action} className="space-y-4">
        <input type="hidden" name="next" value={next} />
        <Field id="email" name="email" type="email" label="Email" autoComplete="email" required defaultValue={state.fields?.email} />
        <div className="space-y-1.5">
          <Field id="password" name="password" type="password" label="Password" autoComplete="current-password" required />
          <Link href="/forgot-password" className="inline-block text-sm text-accent hover:underline">
            Forgot your password?
          </Link>
        </div>
        <FormMessage state={state} />
        <SubmitButton pending="Signing in...">Sign in</SubmitButton>
      </form>
    </AuthCard>
  );
}
