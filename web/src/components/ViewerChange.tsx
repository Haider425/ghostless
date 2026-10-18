"use client";

import { useEffect } from "react";

import { adoptGuestDraft, importGuestResume, resetForViewer } from "@/lib/resume";
import { resetSavedForViewer } from "@/lib/saved";

import { useSite } from "./SiteContext";

// who this page last showed data for; survives client-side navigation, not reloads
let lastViewer: number | null | undefined;

/**
 * Keeps per-person data with its person. When someone different signs in or
 * out, everything cached for the previous person is dropped. When someone
 * signs in, what they did as a guest in this browser (a resume check, a
 * builder draft) moves into their account and out of the browser, so the
 * next person to use it never sees it.
 */
export function ViewerChange() {
  const { viewer } = useSite();
  const id = viewer?.id ?? null;

  useEffect(() => {
    if (lastViewer !== undefined && lastViewer !== id) {
      resetForViewer(id);
      resetSavedForViewer();
    } else {
      resetForViewer(id); // first render: record who this is (caches are empty anyway)
    }
    lastViewer = id;
    if (id !== null) {
      adoptGuestDraft(id);
      void importGuestResume();
    }
  }, [id]);

  return null;
}
