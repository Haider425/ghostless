"use client";

import Link from "next/link";
import { type ReactNode, useActionState } from "react";

import { type FormState, signUp } from "@/app/actions/auth";
import { AuthCard, Field, FormMessage, SubmitButton } from "@/components/Form";

export function SignupForm({ next, oauth, notice }: { next: string; oauth?: ReactNode; notice?: string | null }) {
  const [state, action] = useActionState<FormState, FormData>(signUp, {});
  return (
    <AuthCard
      title="Create your account"
      lead="Free. Save jobs, keep your resumes, and see how you match every posting, on any device."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
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
        <Field id="name" name="name" label="Name" autoComplete="name" maxLength={80} defaultValue={state.fields?.name} hint="Optional. Only shown to you." />
        <Field id="email" name="email" type="email" label="Email" autoComplete="email" required defaultValue={state.fields?.email} />
        <Field
          id="password"
          name="password"
          type="password"
          label="Password"
          autoComplete="new-password"
          required
          minLength={10}
          hint="At least 10 characters. A short phrase is easy to remember and hard to guess."
        />
        <label className="flex items-start gap-2.5 text-sm text-ink-soft">
          <input type="checkbox" name="terms" required className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]" />
          <span>
            I agree to the{" "}
            <Link href="/terms" className="text-accent hover:underline">terms</Link> and{" "}
            <Link href="/privacy" className="text-accent hover:underline">privacy policy</Link>.
          </span>
        </label>
        <FormMessage state={state} />
        <SubmitButton pending="Creating your account...">Create account</SubmitButton>
      </form>
    </AuthCard>
  );
}
