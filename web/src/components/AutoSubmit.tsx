"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { type SearchParams, jobsHref, parseFilters } from "@/lib/filters";

/**
 * Enhances a GET filter form:
 *  - submits as soon as a checkbox, radio or select changes
 *  - builds the URL with the same jobsHref() the server uses, so defaults and
 *    empty values are left out and the page always resets to 1
 *  - navigates client-side instead of a full page reload
 *
 * Fields can live outside the form (the sort menu uses the `form`
 * attribute), so events are matched by `element.form`, not by DOM position.
 * Without JavaScript the form still submits normally.
 *
 * Choosing a radio option closes its dropdown; checkboxes keep it open so
 * several can be picked. (PopoverManager handles the rest of dropdown behaviour.)
 */
export function AutoSubmit({ formId }: { formId: string }) {
  // jobs filter form only: URLs are built with jobsHref()
  const router = useRouter();

  useEffect(() => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) return;

    const popovers = () => [...document.querySelectorAll<HTMLDetailsElement>("details[data-popover][open]")];

    const go = () => {
      const params: SearchParams = {};
      for (const [key, value] of new FormData(form)) {
        if (typeof value !== "string") continue;
        const existing = params[key];
        params[key] = existing === undefined ? value : [...(Array.isArray(existing) ? existing : [existing]), value];
      }
      router.push(jobsHref({ ...parseFilters(params), page: 1 }), { scroll: false });
    };

    const onChange = (event: Event) => {
      const target = event.target;
      const isOption =
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLInputElement && (target.type === "checkbox" || target.type === "radio"));
      if (!isOption || (target as HTMLInputElement | HTMLSelectElement).form !== form) return;
      // a single choice closes its dropdown; checkboxes keep it open for picking several
      if (target instanceof HTMLInputElement && target.type === "radio") popovers().forEach((d) => (d.open = false));
      go();
    };
    const onSubmit = (event: SubmitEvent) => {
      if (event.target === form) {
        event.preventDefault();
        popovers().forEach((d) => (d.open = false));
        go();
      }
    };

    document.addEventListener("change", onChange);
    document.addEventListener("submit", onSubmit);
    return () => {
      document.removeEventListener("change", onChange);
      document.removeEventListener("submit", onSubmit);
    };
  }, [formId, router]);

  return null;
}
