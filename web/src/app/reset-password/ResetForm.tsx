"use client";

import Link from "next/link";
import { useActionState } from "react";

import { type FormState, resetPassword } from "@/app/actions/auth";
import { AuthCard, Field, FormMessage, SubmitButton } from "@/components/Form";

export function ResetForm({ token }: { token: string }) {
  const [state, action] = useActionState<FormState, FormData>(resetPassword, {});
  return (
    <AuthCard title="Choose a new password" lead="You'll be signed out on every other device.">
      <form action={action} className="space-y-4">
        <input type="hidden" name="token" value={token} />
        <Field id="password" name="password" type="password" label="New password" autoComplete="new-password" required minLength={10} hint="At least 10 characters." />
        <FormMessage state={state} />
        {state.error?.includes("expired") && (
          <Link href="/forgot-password" className="block text-sm font-medium text-accent hover:underline">Send a new reset link</Link>
        )}
        <SubmitButton pending="Saving...">Save new password</SubmitButton>
      </form>
    </AuthCard>
  );
}
