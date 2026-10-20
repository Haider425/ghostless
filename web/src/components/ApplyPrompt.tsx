"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { Application } from "@/lib/api-types";
import {
  APPLY_EVENT,
  type ApplyJob,
  MIN_AWAY_MS,
  answerApplication,
  pendingApplication,
} from "@/lib/applications";
import { noteSavedOnAccount, saveLocally } from "@/lib/saved";

import { CheckIcon, CloseIcon } from "./Icons";
import { useSite } from "./SiteContext";

type Phase =
  | { kind: "ask" }
  | { kind: "saving" }
  | { kind: "done"; text: string; link?: { href: string; label: string } }
  | { kind: "error" };

const STATUS_WORDS: Record<Application["status"], string> = {
  saved: "saved",
  applied: "applied",
  interviewing: "interviewing",
  offer: "an offer",
  rejected: "not moving forward",
};

/**
 * Asks "did you apply?" when someone comes back from an employer's site
 * (ApplyLink notes the visit). Non-blocking: it sits in a corner, keeps focus
 * where it was, and goes away on "Not yet", the close button or Escape.
 * Answering in one tab clears it in the others.
 */
export function ApplyPrompt() {
  const { viewer } = useSite();
  const [job, setJob] = useState<ApplyJob | null>(null);
  const [phase, setPhaseState] = useState<Phase>({ kind: "ask" });
  // read by the storage listeners, which can run before React re-renders: kept in step by hand
  const phaseRef = useRef(phase);
  const setPhase = (next: Phase) => {
    phaseRef.current = next;
    setPhaseState(next);
  };

  useEffect(() => {
    const check = () => {
      if (document.visibilityState !== "visible") return;
      const pending = pendingApplication();
      const busy = phaseRef.current.kind !== "ask";
      if (pending && Date.now() - pending.at >= MIN_AWAY_MS) {
        if (!busy) setJob(pending.job);
      } else if (!pending && !busy) {
        setJob(null); // answered in another tab, or forgotten
      }
    };
    const first = window.setTimeout(check, 0); // a visit noted before this page loaded
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    window.addEventListener("storage", check);
    window.addEventListener(APPLY_EVENT, check);
    return () => {
      window.clearTimeout(first);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
      window.removeEventListener("storage", check);
      window.removeEventListener(APPLY_EVENT, check);
    };
  }, []);

  // a confirmation fades out on its own
  useEffect(() => {
    if (phase.kind !== "done") return;
    const timer = window.setTimeout(() => {
      setJob(null);
      phaseRef.current = { kind: "ask" };
      setPhaseState({ kind: "ask" });
    }, 8000);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (!job) return null;

  function dismiss() {
    if (job) answerApplication(job.id, "not_yet");
    setJob(null);
    setPhase({ kind: "ask" });
  }

  async function applied(current: ApplyJob) {
    if (!viewer) {
      setPhase({
        kind: "done",
        text: "Saved in this browser. Create a free account to track where each application stands.",
        link: { href: "/signup?next=/saved", label: "Create an account" },
      });
      saveLocally(current);
      answerApplication(current.id, "applied");
      return;
    }
    setPhase({ kind: "saving" });
    try {
      const response = await fetch(`/api/applications?id=${current.id}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source: "apply_prompt" }),
      });
      if (!response.ok) throw new Error(String(response.status));
      const result = (await response.json()) as Application;
      answerApplication(current.id, "applied");
      noteSavedOnAccount(current.id);
      setPhase({
        kind: "done",
        text:
          result.changed || result.status === "applied"
            ? "Tracking it as applied."
            : `Already tracked: ${STATUS_WORDS[result.status]}.`,
        link: { href: "/saved", label: "Your applications" },
      });
    } catch {
      setPhase({ kind: "error" });
    }
  }

  return (
    <section
      aria-label="Did you apply?"
      aria-live="polite"
      onKeyDown={(event) => event.key === "Escape" && phase.kind !== "saving" && dismiss()}
      className="apply-prompt fixed inset-x-3 bottom-3 z-50 overflow-hidden rounded-2xl border border-accent/50 bg-surface shadow-[0_24px_64px_-12px_rgb(0_0_0/0.45)] sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-[26rem]"
    >
      <button
        type="button"
        onClick={dismiss}
        disabled={phase.kind === "saving"}
        className="btn btn-ghost btn-sm absolute top-3 right-3 z-10 size-8 px-0"
      >
        <CloseIcon className="size-4" />
        <span className="sr-only">Close</span>
      </button>
      <div className="flex items-start gap-3 bg-accent-tint px-5 pt-4 pb-3.5 pr-12">
        <span aria-hidden="true" className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-accent-solid text-on-accent">
          <CheckIcon className="size-4.5" />
        </span>
        <div className="min-w-0">
          <p className="text-base font-bold text-ink">{phase.kind === "done" ? "Got it" : "Did you apply?"}</p>
          <p className="mt-0.5 text-sm text-ink-soft">
            <span className="font-semibold text-ink">{job.title}</span> at {job.company}
          </p>
        </div>
      </div>
      <div className="px-5 pt-3.5 pb-4">
        {phase.kind === "done" ? (
          <p className="text-ui text-ink">
            {phase.text}{" "}
            {phase.link && (
              <Link href={phase.link.href} className="link" onClick={() => setJob(null)}>
                {phase.link.label}
              </Link>
            )}
          </p>
        ) : (
          <>
            {phase.kind === "error" && (
              <p role="alert" className="mb-3 text-sm text-danger">
                That didn&apos;t save. Check your connection and try again.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => applied(job)}
                disabled={phase.kind === "saving"}
                className="btn btn-primary"
              >
                {phase.kind === "saving" ? "Saving..." : "Yes, I applied"}
              </button>
              <button type="button" onClick={dismiss} disabled={phase.kind === "saving"} className="btn btn-secondary">
                Not yet
              </button>
            </div>
            <p className="mt-3 text-xs text-ink-faint">
              Only you know: Ghostless can&apos;t see the employer&apos;s site, so it records what you tell it.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
