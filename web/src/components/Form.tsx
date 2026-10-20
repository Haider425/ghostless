"use client";

import type { InputHTMLAttributes, ReactNode } from "react";
import { useFormStatus } from "react-dom";

import type { FormState } from "@/app/actions/auth";

export const inputClass =
  "field";

export function Field({
  label,
  hint,
  id,
  ...input
}: { label: string; hint?: ReactNode; id: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-semibold text-ink">
        {label}
      </label>
      <input id={id} className={inputClass} aria-describedby={hint ? `${id}-hint` : undefined} {...input} />
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-ink-soft">
          {hint}
        </p>
      )}
    </div>
  );
}

export function SubmitButton({ children, pending, tone = "primary" }: { children: ReactNode; pending?: string; tone?: "primary" | "danger" | "secondary" }) {
  // primary buttons fill their form (sign in, sign up); secondary and danger actions stay their own size
  const status = useFormStatus();
  const styles = { primary: "btn-primary", danger: "btn-danger", secondary: "btn-secondary" }[tone];
  return (
    <button type="submit" disabled={status.pending} className={`btn ${tone === "primary" ? "btn-lg w-full" : ""} ${styles}`}>
      {status.pending ? (pending ?? "Working...") : children}
    </button>
  );
}

export function FormMessage({ state }: { state: FormState }) {
  if (state.error) {
    return (
      <p role="alert" className="notice notice-danger">
        {state.error}
      </p>
    );
  }
  if (state.message) {
    return (
      <p role="status" className="notice">
        {state.message}
      </p>
    );
  }
  return null;
}

export function AuthCard({ title, lead, children, footer }: { title: string; lead?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="mx-auto max-w-[25rem] px-4 pt-14 pb-24 sm:pt-24">
      <h1 className="text-4xl font-bold tracking-[-0.03em] text-ink">{title}</h1>
      {lead && <p className="mt-2.5 text-base text-ink-soft">{lead}</p>}
      <div className="mt-7">{children}</div>
      {footer && <div className="mt-6 text-center text-ui text-ink-soft">{footer}</div>}
    </div>
  );
}
