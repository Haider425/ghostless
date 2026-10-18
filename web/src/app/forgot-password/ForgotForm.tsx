"use client";

import Link from "next/link";
import { useActionState } from "react";

import { type FormState, forgotPassword } from "@/app/actions/auth";
import { AuthCard, Field, FormMessage, SubmitButton } from "@/components/Form";

export function ForgotForm() {
  const [state, action] = useActionState<FormState, FormData>(forgotPassword, {});
  return (
    <AuthCard
      title="Reset your password"
      lead="Enter your account's email and we'll send a link to choose a new password."
      footer={<Link href="/login" className="text-accent hover:underline">Back to sign in</Link>}
    >
      <form action={action} className="space-y-4">
        <Field id="email" name="email" type="email" label="Email" autoComplete="email" required defaultValue={state.fields?.email} />
        <FormMessage state={state} />
        {!state.message && <SubmitButton pending="Sending...">Send reset link</SubmitButton>}
      </form>
    </AuthCard>
  );
}
