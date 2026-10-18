"use client";

import { usePathname } from "next/navigation";
import { type FormEvent, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { CloseIcon } from "./Icons";
import { useSite } from "./SiteContext";

const noop = () => () => {};

const CATEGORIES = [
  { value: "wrong_job_info", label: "Wrong information on a job", forJobs: true },
  { value: "broken_link", label: "A link doesn't work", forJobs: true },
  { value: "site_bug", label: "Something on the site is broken", forJobs: false },
  { value: "suggestion", label: "An idea or a company to add", forJobs: false },
  { value: "other", label: "Something else", forJobs: false },
] as const;

/**
 * "Report a problem": a native <dialog> with a short form. Reports go to the
 * admin dashboard. On a job page the job is attached automatically.
 */
export function ReportDialog({
  jobId,
  label = "Report a problem",
  className,
}: {
  jobId?: number;
  label?: string;
  className?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const pathname = usePathname();
  const { viewer } = useSite();
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState("");

  function open() {
    setState("idle");
    setError("");
    dialog.current?.showModal();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setState("sending");
    const response = await fetch("/api/reports", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        category: form.get("category"),
        message: form.get("message"),
        email: form.get("email"),
        job_id: jobId ?? null,
        page: pathname,
      }),
    }).catch(() => null);
    if (response?.ok) {
      setState("sent");
      return;
    }
    const data = (await response?.json().catch(() => null)) as { detail?: string } | null;
    setError(data?.detail ?? "That didn't go through. Check your connection and try again.");
    setState("error");
  }

  // The dialog renders at the end of <body>, so the trigger can sit inside a
  // paragraph or list item (a <dialog> can't legally go there).
  const onClient = useSyncExternalStore(noop, () => true, () => false);

  return (
    <>
      <button type="button" onClick={open} className={className ?? "text-left hover:text-ink hover:underline"}>
        {label}
      </button>
      {onClient && createPortal(
      <dialog
        ref={dialog}
        aria-labelledby="report-title"
        className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-2xl border border-line bg-surface p-0 text-ink shadow-pop"
        onClick={(e) => e.target === dialog.current && dialog.current?.close()}
      >
        <div className="p-5 sm:p-6">
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 id="report-title" className="text-xl font-semibold">
              {state === "sent" ? "Thanks for telling us" : jobId ? "Report a problem with this job" : "Report a problem"}
            </h2>
            <button type="button" onClick={() => dialog.current?.close()} className="grid size-8 place-items-center rounded-md text-ink-soft hover:bg-sunken">
              <CloseIcon className="size-4" />
              <span className="sr-only">Close</span>
            </button>
          </div>
          {state === "sent" ? (
            <div className="space-y-4">
              <p className="text-ink-soft">Your report reached the Ghostless team. Reports about job data are usually checked within a day.</p>
              <button type="button" onClick={() => dialog.current?.close()} className="h-10 rounded-lg bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover">
                Done
              </button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <fieldset className="space-y-1.5">
                <legend className="mb-1 text-sm font-medium">What&apos;s wrong?</legend>
                {CATEGORIES.filter((c) => jobId || !c.forJobs || c.value === "broken_link").map((c, i) => (
                  <label key={c.value} className="flex items-center gap-2.5 text-sm">
                    <input type="radio" name="category" value={c.value} defaultChecked={i === 0} required className="size-4 accent-[var(--accent)]" />
                    {c.label}
                  </label>
                ))}
              </fieldset>
              <div className="space-y-1.5">
                <label htmlFor="report-message" className="text-sm font-medium">Details</label>
                <textarea
                  id="report-message"
                  name="message"
                  required
                  minLength={3}
                  maxLength={4000}
                  rows={4}
                  placeholder={jobId ? "For example: this job is closed on their site, or the pay is wrong" : "What happened, and on which page?"}
                  className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 placeholder:text-ink-faint focus:border-accent focus:outline-none"
                />
              </div>
              {!viewer && (
                <div className="space-y-1.5">
                  <label htmlFor="report-email" className="text-sm font-medium">
                    Email <span className="font-normal text-ink-soft">(optional, if you&apos;d like a reply)</span>
                  </label>
                  <input id="report-email" name="email" type="email" maxLength={254} className="h-10 w-full rounded-lg border border-line-strong bg-surface px-3 focus:border-accent focus:outline-none" />
                </div>
              )}
              {state === "error" && <p role="alert" className="rounded-lg bg-brick-tint px-3 py-2 text-sm text-brick">{error}</p>}
              <div className="flex items-center gap-3">
                <button type="submit" disabled={state === "sending"} className="h-10 rounded-lg bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover disabled:opacity-60">
                  {state === "sending" ? "Sending..." : "Send report"}
                </button>
                <button type="button" onClick={() => dialog.current?.close()} className="h-10 rounded-lg px-3 text-ink-soft hover:bg-sunken">
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      </dialog>,
        document.body,
      )}
    </>
  );
}
