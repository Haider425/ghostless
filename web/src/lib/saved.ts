"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

import { useSite } from "@/components/SiteContext";

/*
  Saved jobs.

  Signed out: kept in this browser (localStorage), with enough detail to list
  them without asking the server. Signed in: kept on the account, so they
  follow the person to other devices. On the first signed-in visit, anything
  saved in the browser is moved to the account.

  Storage can be unavailable (private windows, blocked site data), so every
  access is guarded and the list simply comes back empty.
*/

export interface SavedJob {
  id: number;
  title: string;
  company: string;
  companyDomain: string | null;
  location: string | null;
  url: string;
  savedAt: string;
}

const KEY = "ghostless:saved:v1";
const EVENT = "ghostless:saved";
const EMPTY: SavedJob[] = [];

// ---------- browser storage ----------

let localCache: { raw: string | null; jobs: SavedJob[] } = { raw: null, jobs: EMPTY };

function readLocal(): SavedJob[] {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return EMPTY;
  }
  if (raw === localCache.raw) return localCache.jobs;
  let jobs: SavedJob[] = EMPTY;
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (Array.isArray(parsed)) jobs = parsed.filter((j): j is SavedJob => typeof j?.id === "number");
  } catch {
    jobs = EMPTY;
  }
  localCache = { raw, jobs };
  return jobs;
}

function writeLocal(jobs: SavedJob[]): void {
  try {
    if (jobs.length) window.localStorage.setItem(KEY, JSON.stringify(jobs));
    else window.localStorage.removeItem(KEY);
  } catch {
    // storage full or blocked: the save is lost, nothing else breaks
  }
  notify();
}

// ---------- account ----------

let remote: { loaded: boolean; ids: number[] } = { loaded: false, ids: [] };
let loading: Promise<void> | null = null;

function setRemote(ids: number[]) {
  remote = { loaded: true, ids };
  notify();
}

async function loadRemote(): Promise<void> {
  const response = await fetch("/api/saved", { cache: "no-store" });
  if (!response.ok) return;
  let ids = (await response.json()) as number[];
  const local = readLocal();
  if (local.length) {
    // move jobs saved before signing in onto the account
    const merged = await fetch("/api/saved", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ job_ids: local.map((j) => j.id) }),
    });
    if (merged.ok) {
      ids = (await merged.json()) as number[];
      writeLocal([]);
    }
  }
  setRemote(ids);
}

/** Forget the previous person's saved jobs (the next account's list loads fresh). */
export function resetSavedForViewer(): void {
  remote = { loaded: false, ids: [] };
  loading = null;
  notify();
}

// ---------- subscription ----------

function notify() {
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange); // other tabs
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

const getRemote = () => remote;
const serverRemote = () => remote;

export function useSavedJobs() {
  const { viewer } = useSite();
  const signedIn = Boolean(viewer);
  const local = useSyncExternalStore(subscribe, readLocal, () => EMPTY);
  const account = useSyncExternalStore(subscribe, getRemote, serverRemote);

  useEffect(() => {
    if (signedIn && !remote.loaded && !loading) {
      loading = loadRemote().finally(() => {
        loading = null;
      });
    }
    if (!signedIn && remote.loaded) {
      remote = { loaded: false, ids: [] }; // signed out: forget the account's list
      notify();
    }
  }, [signedIn]);

  const ids = signedIn ? account.ids : local.map((j) => j.id);
  const isSaved = useCallback((id: number) => ids.includes(id), [ids]);

  const toggle = useCallback(
    async (job: Omit<SavedJob, "savedAt">) => {
      if (!signedIn) {
        const current = readLocal();
        writeLocal(
          current.some((j) => j.id === job.id)
            ? current.filter((j) => j.id !== job.id)
            : [{ ...job, savedAt: new Date().toISOString() }, ...current],
        );
        return;
      }
      const saved = remote.ids.includes(job.id);
      setRemote(saved ? remote.ids.filter((id) => id !== job.id) : [job.id, ...remote.ids]); // optimistic
      const response = saved
        ? await fetch(`/api/saved?id=${job.id}`, { method: "DELETE" })
        : await fetch("/api/saved", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ job_ids: [job.id] }),
          });
      if (response.ok) setRemote((await response.json()) as number[]);
      else setRemote(saved ? [job.id, ...remote.ids] : remote.ids.filter((id) => id !== job.id)); // undo
    },
    [signedIn],
  );

  const removeLocal = useCallback((id: number) => writeLocal(readLocal().filter((j) => j.id !== id)), []);

  return { signedIn, ids, count: ids.length, local, isSaved, toggle, removeLocal };
}
