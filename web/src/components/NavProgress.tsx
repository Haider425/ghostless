"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * A thin bar along the top of the window while the next page renders on the
 * server, so a click is acknowledged at once. It waits 120ms before showing,
 * so quick navigations don't flash, and clears when the new route arrives.
 * Pages without JavaScript navigate normally and never see it.
 */
export function NavProgress() {
  const route = `${usePathname()}?${useSearchParams().toString()}`;
  const current = useRef(route);
  useEffect(() => {
    current.current = route;
  }, [route]);
  // the route a click left from: the bar shows until the route is a different one
  const [leaving, setLeaving] = useState<string | null>(null);
  const active = leaving === route;

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    function onClick(event: MouseEvent) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a[href]");
      if (!(link instanceof HTMLAnchorElement) || link.target || link.hasAttribute("download")) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || (url.pathname === location.pathname && url.search === location.search)) return;
      const from = location.href;
      clearTimeout(timer);
      // only if still on the old page: a navigation quicker than the delay needs no bar
      timer = setTimeout(() => location.href === from && setLeaving(current.current), 120);
    }
    // capture: Next's <Link> cancels the click's default to route on the client, so look before it does
    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!active) return;
    const giveUp = setTimeout(() => setLeaving(null), 10_000);
    return () => clearTimeout(giveUp);
  }, [active]);

  if (!active) return null;
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden">
      <div className="nav-progress h-full bg-accent" />
    </div>
  );
}
