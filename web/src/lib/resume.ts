"use client";

import { useEffect, useSyncExternalStore } from "react";

import { useSite } from "@/components/SiteContext";

import type { Analysis, Match } from "./api-types";

/*
  The resume used for match scores.

  Signed out: the latest analysis is kept in this browser only (the file
  itself is never stored anywhere). Signed in: the account's primary resume,
  and only that: a copy kept in the browser is moved into the account at
  sign-in (importGuestResume), never shown to whoever is signed in.

  Everything held in memory remembers which account it belongs to and is
  dropped when a different person signs in (resetForViewer).
*/

export interface ActiveResume {
  source: "browser" | "account";
  id: number | null; // account resumes only
  title: string;
  analysis: Analysis;
  updatedAt: string;
}

const KEY = "ghostless:resume:v1";
const EVENT = "ghostless:resume";

let localCache: { raw: string | null; value: ActiveResume | null } = { raw: null, value: null };

function readLocal(): ActiveResume | null {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
  if (raw === localCache.raw) return localCache.value;
  let value: ActiveResume | null = null;
  try {
    const parsed = raw ? (JSON.parse(raw) as ActiveResume) : null;
    if (parsed?.analysis?.profile) value = { ...parsed, source: "browser", id: null };
  } catch {
    value = null;
  }
  localCache = { raw, value };
  return value;
}

export function saveLocalResume(title: string, analysis: Analysis): void {
  try {
    const value: ActiveResume = { source: "browser", id: null, title, analysis, updatedAt: new Date().toISOString() };
    window.localStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // blocked storage: the analysis still shows, it just isn't remembered
  }
  window.dispatchEvent(new Event(EVENT));
}

export function clearLocalResume(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

/** Builder drafts are kept per person, so whoever uses this browser next never sees them. */
export function draftKey(userId: number | null | undefined): string {
  return userId ? `ghostless:builder:v1:u${userId}` : "ghostless:builder:v1";
}

/** Move a draft started before signing in to the person's own draft (unless they already have one). */
export function adoptGuestDraft(userId: number): void {
  try {
    const guest = window.localStorage.getItem(draftKey(null));
    if (!guest) return;
    if (!window.localStorage.getItem(draftKey(userId))) window.localStorage.setItem(draftKey(userId), guest);
    window.localStorage.removeItem(draftKey(null));
  } catch {
    // storage blocked: nothing was kept to begin with
  }
}

// ---------- account ----------

let account: { userId: number | null; loaded: boolean; value: ActiveResume | null } = {
  userId: null,
  loaded: false,
  value: null,
};
let loading: Promise<void> | null = null;
let viewerId: number | null = null; // who is signed in, as far as this page knows

/** Forget everything cached for the previous person. */
export function resetForViewer(id: number | null): void {
  viewerId = id;
  account = { userId: null, loaded: false, value: null };
  loading = null;
  scoreCache.clear();
  window.dispatchEvent(new Event(EVENT));
}

export function refreshAccountResume(): Promise<void> {
  const forUser = viewerId;
  loading = fetch("/api/resume/active", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null))
    .then((data: { id: number; title: string; analysis: Analysis; updated_at: string } | null) => {
      if (forUser !== viewerId) return; // someone else signed in meanwhile: drop it
      account = {
        userId: forUser,
        loaded: true,
        value: data ? { source: "account", id: data.id, title: data.title, analysis: data.analysis, updatedAt: data.updated_at } : null,
      };
      window.dispatchEvent(new Event(EVENT));
    })
    .catch(() => {})
    .finally(() => {
      loading = null;
    });
  return loading;
}

/** Move a resume checked before signing in into the account, then remove the browser copy. */
export async function importGuestResume(): Promise<void> {
  const guest = readLocal();
  if (!guest) return;
  const response = await fetch("/api/resumes/import", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title: guest.title || "My resume", analysis: guest.analysis }),
  }).catch(() => null);
  // moved, or the account is full (20 resumes): either way the browser copy goes,
  // so it can't be shown to whoever uses this browser next
  if (response && (response.ok || response.status === 400)) clearLocalResume();
  if (response?.ok) await refreshAccountResume();
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

const getAccount = () => account;

/** The resume to score jobs with, or null. `ready` is false until it's known. */
export function useActiveResume(): { resume: ActiveResume | null; ready: boolean } {
  const { viewer } = useSite();
  const local = useSyncExternalStore(subscribe, readLocal, () => null);
  const remote = useSyncExternalStore(subscribe, getAccount, getAccount);
  const id = viewer?.id ?? null;
  useEffect(() => {
    if (id !== null && account.userId !== id && !loading) {
      viewerId = id;
      void refreshAccountResume();
    }
  }, [id]);
  if (id === null) return { resume: local, ready: true };
  const mine = remote.userId === id;
  return { resume: mine ? remote.value : null, ready: mine && remote.loaded };
}

/** Body for /api/resume/match and /api/resume/recommendations. */
export function resumeQuery(resume: ActiveResume): { resume_id: number } | { profile: Analysis["profile"] } {
  return resume.id !== null ? { resume_id: resume.id } : { profile: resume.analysis.profile };
}

// ---------- match scores for a page of jobs ----------

const scoreCache = new Map<string, Match>();

export async function fetchMatches(resume: ActiveResume, jobIds: number[]): Promise<Record<number, Match>> {
  const keyOf = (id: number) => `${resume.source}:${resume.id ?? resume.updatedAt}:${id}`;
  const missing = jobIds.filter((id) => !scoreCache.has(keyOf(id)));
  if (missing.length) {
    const response = await fetch("/api/resume/match", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...resumeQuery(resume), job_ids: missing.slice(0, 100) }),
    }).catch(() => null);
    if (response?.ok) {
      const data = (await response.json()) as Record<string, Match>;
      for (const [id, match] of Object.entries(data)) scoreCache.set(keyOf(Number(id)), match);
    }
  }
  const out: Record<number, Match> = {};
  for (const id of jobIds) {
    const match = scoreCache.get(keyOf(id));
    if (match) out[id] = match;
  }
  return out;
}

export function scoreTone(score: number): "strong" | "good" | "fair" | "low" {
  if (score >= 65) return "strong";
  if (score >= 50) return "good";
  if (score >= 35) return "fair";
  return "low";
}
