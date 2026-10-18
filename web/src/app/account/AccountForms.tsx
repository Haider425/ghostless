"use client";

import { useActionState } from "react";

import {
  type FormState,
  changePassword,
  deleteAccount,
  resendVerification,
  signOutEverywhere,
  unlinkProvider,
  updateName,
} from "@/app/actions/auth";
import { Field, FormMessage, SubmitButton } from "@/components/Form";

export function NameForm({ name }: { name: string }) {
  const [state, action] = useActionState<FormState, FormData>(updateName, {});
  return (
    <form action={action} className="space-y-3">
      <Field id="name" name="name" label="Name" defaultValue={name} maxLength={80} autoComplete="name" />
      <FormMessage state={state} />
      <SubmitButton tone="secondary" pending="Saving...">Save name</SubmitButton>
    </form>
  );
}

export function VerifyNotice() {
  const [state, action] = useActionState<FormState>(resendVerification, {});
  return (
    <form action={action} className="mt-3 space-y-3">
      <p className="text-sm text-ink-soft">Check your inbox for the confirmation link. Didn&apos;t get it?</p>
      <FormMessage state={state} />
      <SubmitButton tone="secondary" pending="Sending...">Send it again</SubmitButton>
    </form>
  );
}

export function PasswordForm({ hasPassword = true }: { hasPassword?: boolean }) {
  const [state, action] = useActionState<FormState, FormData>(changePassword, {});
  return (
    <form action={action} className="space-y-3">
      {hasPassword ? (
        <Field id="current_password" name="current_password" type="password" label="Current password" autoComplete="current-password" required />
      ) : (
        <p className="text-sm text-ink-soft">
          You sign in with Google or GitHub. Add a password to also sign in with your email.
        </p>
      )}
      <Field id="new_password" name="new_password" type="password" label="New password" autoComplete="new-password" required minLength={10} hint="At least 10 characters." />
      <Field id="confirm_password" name="confirm_password" type="password" label="Confirm new password" autoComplete="new-password" required minLength={10} />
      <FormMessage state={state} />
      <SubmitButton tone="secondary" pending="Saving...">{hasPassword ? "Change password" : "Set password"}</SubmitButton>
    </form>
  );
}

export function SessionsForm() {
  const [state, action] = useActionState<FormState>(signOutEverywhere, {});
  return (
    <form action={action} className="space-y-3">
      <FormMessage state={state} />
      <SubmitButton tone="secondary" pending="Signing out...">Sign out of other devices</SubmitButton>
    </form>
  );
}

/** Disconnect a linked Google or GitHub sign-in. */
export function UnlinkProvider({ provider, label }: { provider: "google" | "github"; label: string }) {
  const [state, action] = useActionState<FormState, FormData>(unlinkProvider, {});
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="provider" value={provider} />
      <SubmitButton tone="secondary" pending="Disconnecting...">Disconnect {label}</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}

export function DangerZone({ hasPassword = true }: { hasPassword?: boolean }) {
  const [state, action] = useActionState<FormState, FormData>(deleteAccount, {});
  return (
    <details className="group rounded-xl border border-brick/30 p-4">
      <summary className="font-medium text-brick">I want to delete my account</summary>
      <form action={action} className="mt-4 space-y-3">
        <p className="text-sm text-ink-soft">
          This can&apos;t be undone. Reports you sent stay, without your email, so the team can still fix what you found.
        </p>
        {hasPassword && (
          <Field id="delete-password" name="password" type="password" label="Your password" autoComplete="current-password" required />
        )}
        <Field id="confirm" name="confirm" label="Type “delete my account” to confirm" autoComplete="off" required />
        <FormMessage state={state} />
        <SubmitButton tone="danger" pending="Deleting...">Delete my account</SubmitButton>
      </form>
    </details>
  );
}
