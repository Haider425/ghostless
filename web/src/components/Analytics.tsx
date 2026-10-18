"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { useSite } from "./SiteContext";

/**
 * Counts a page view on each navigation, through Ghostless's own API: no
 * third-party scripts, no cookies. Skipped when the visitor turned usage
 * stats off in Settings or asks browsers not to track them.
 */
export function Analytics() {
  const pathname = usePathname();
  const { prefs } = useSite();
  const last = useRef<string | null>(null);

  useEffect(() => {
    if (!prefs.analytics || last.current === pathname) return;
    if (navigator.doNotTrack === "1" || (navigator as { globalPrivacyControl?: boolean }).globalPrivacyControl) return;
    last.current = pathname;
    const body = JSON.stringify({ kind: "pageview", path: pathname, referrer: document.referrer || null });
    if (!navigator.sendBeacon?.("/api/e", new Blob([body], { type: "application/json" }))) {
      fetch("/api/e", { method: "POST", body, headers: { "content-type": "application/json" }, keepalive: true }).catch(() => {});
    }
  }, [pathname, prefs.analytics]);

  return null;
}

/** Report a client error to the admin dashboard. Never throws. */
export function reportClientError(error: Error & { digest?: string }) {
  try {
    const body = JSON.stringify({
      kind: "error",
      path: window.location.pathname,
      message: `${error.name}: ${error.message}`.slice(0, 900),
      digest: error.digest ?? null,
    });
    navigator.sendBeacon?.("/api/e", new Blob([body], { type: "application/json" }));
  } catch {
    // reporting must never cause another error
  }
}
