"use client";

import { useEffect } from "react";

/**
 * Dropdowns are <details data-popover> elements, so they work without
 * JavaScript. This adds the expected behaviour: one open at a time, and
 * closing on Escape or a click outside.
 */
export function PopoverManager() {
  useEffect(() => {
    const open = () => [...document.querySelectorAll<HTMLDetailsElement>("details[data-popover][open]")];
    const onToggle = (event: Event) => {
      const opened = event.target;
      if (opened instanceof HTMLDetailsElement && opened.open && opened.hasAttribute("data-popover")) {
        open().forEach((d) => d !== opened && !d.contains(opened) && (d.open = false));
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      open().forEach((d) => !d.contains(event.target as Node) && (d.open = false));
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      open().forEach((d) => {
        d.open = false;
        d.querySelector("summary")?.focus();
      });
    };
    document.addEventListener("toggle", onToggle, true); // toggle doesn't bubble
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("toggle", onToggle, true);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);
  return null;
}
