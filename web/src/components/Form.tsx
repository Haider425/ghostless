"use client";

import type { InputHTMLAttributes, ReactNode } from "react";
import { useFormStatus } from "react-dom";

import type { FormState } from "@/app/actions/auth";

export const inputClass =
  "field h-10";

export function Field({
  label,
  hint,
  id,
  ...input
}: { label: string; hint?: ReactNode; id: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      <input id={id} className={inputClass} aria-describedby={hint ? `${id}-hint` : undefined} {...input} />
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-ink-soft">
          {hint}
        </p>
      )}
    </div>
  );
}

export function SubmitButton({ children, pending, tone = "primary" }: { children: ReactNode; pending?: string; tone?: "primary" | "danger" | "secondary" }) {
  const status = useFormStatus();
  const styles = {
    primary: "bg-accent-solid text-on-accent hover:bg-accent-hover",
    danger: "bg-brick text-white hover:opacity-90",
    secondary: "border border-line-strong bg-surface text-ink hover:border-ink-faint",
  }[tone];
  return (
    <button type="submit" disabled={status.pending} className={`inline-flex h-11 items-center justify-center rounded-lg px-5 font-medium transition-colors disabled:opacity-60 ${styles}`}>
      {status.pending ? (pending ?? "Working...") : children}
    </button>
  );
}

export function FormMessage({ state }: { state: FormState }) {
  if (state.error) {
    return (
      <p role="alert" className="rounded-lg bg-brick-tint px-3 py-2 text-sm text-brick">
        {state.error}
      </p>
    );
  }
  if (state.message) {
    return (
      <p role="status" className="rounded-lg bg-good-tint px-3 py-2 text-sm text-good">
        {state.message}
      </p>
    );
  }
  return null;
}

export function AuthCard({ title, lead, children, footer }: { title: string; lead?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="mx-auto max-w-md px-4 py-12 sm:py-16">
      <div className="panel p-6 sm:p-8">
        <h1 className="text-3xl font-semibold text-ink">{title}</h1>
        {lead && <p className="mt-2 text-ink-soft">{lead}</p>}
        <div className="mt-6">{children}</div>
      </div>
      {footer && <div className="mt-5 text-center text-sm text-ink-soft">{footer}</div>}
    </div>
  );
}
