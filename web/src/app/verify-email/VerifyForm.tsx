"use client";

import Link from "next/link";
import { useActionState } from "react";

import { type FormState, verifyEmail } from "@/app/actions/auth";
import { AuthCard, FormMessage, SubmitButton } from "@/components/Form";

export function VerifyForm({ token }: { token: string }) {
  const [state, action] = useActionState<FormState, FormData>(verifyEmail, {});
  return (
    <AuthCard title="Confirm your email" lead="One click and you're done. This lets you reset your password if you ever forget it.">
      {state.message ? (
        <div className="space-y-4">
          <FormMessage state={state} />
          <Link href="/jobs" className="inline-flex h-11 items-center rounded-lg bg-accent px-5 font-medium text-on-accent">Browse jobs</Link>
        </div>
      ) : (
        <form action={action} className="space-y-4">
          <input type="hidden" name="token" value={token} />
          <FormMessage state={state} />
          <SubmitButton pending="Confirming...">Confirm my email</SubmitButton>
        </form>
      )}
    </AuthCard>
  );
}
