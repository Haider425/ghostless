"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { CompanyLogo } from "./CompanyLogo";
import { ChevronRightIcon, SearchIcon } from "./Icons";

type Suggestions = {
  companies: { name: string; slug: string; domain: string | null; open: number }[];
  jobs: { id: number; title: string; company: string; domain: string | null; meta: string }[];
};
type Option = { key: string; href: string };

/**
 * The home page's search box. Typing shows up to five matches (companies,
 * then jobs) under the box; Enter, or "See all results", searches all jobs.
 * A plain GET form underneath, so it still searches without JavaScript.
 * Follows the ARIA combobox pattern: arrow keys move through the list,
 * Escape closes it.
 */
export function HomeSearch() {
  const router = useRouter();
  const id = useId();
  const listId = `${id}-list`;
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ q: string; data: Suggestions } | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const box = useRef<HTMLDivElement>(null);

  const query = q.trim();
  useEffect(() => {
    if (query.length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const response = await fetch(`/api/search/suggest?q=${encodeURIComponent(query)}`, { signal: controller.signal }).catch(() => null);
      if (!response?.ok) return;
      const data = (await response.json().catch(() => null)) as Suggestions | null;
      if (data) setResults({ q: query, data });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  // close when focus or a click goes elsewhere
  useEffect(() => {
    const onDown = (event: PointerEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, []);

  const fresh = results && results.q === query && query.length >= 2 ? results.data : null;
  const all = `/jobs?q=${encodeURIComponent(query)}`;
  const options: Option[] = fresh
    ? [
        ...fresh.companies.map((c) => ({ key: `c-${c.slug}`, href: `/companies/${c.slug}` })),
        ...fresh.jobs.map((j) => ({ key: `j-${j.id}`, href: `/jobs/${j.id}` })),
        { key: "all", href: all },
      ]
    : [];
  const showing = open && options.length > 0;
  const optionId = (i: number) => `${id}-opt-${i}`;

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!options.length) return;
      event.preventDefault();
      setOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      // -1 is the text box itself; moving past either end wraps around through it
      setActive((i) => {
        const next = i + step;
        if (next >= options.length) return -1;
        if (next < -1) return options.length - 1;
        return next;
      });
    } else if (event.key === "Escape" && showing) {
      // the first Escape closes the list; only a second one clears the box (the browser's default)
      event.preventDefault();
      setOpen(false);
      setActive(-1);
    } else if (event.key === "Enter" && showing && active >= 0) {
      event.preventDefault();
      router.push(options[active]!.href);
    }
  }

  const row = (i: number) =>
    `flex items-center gap-3 rounded-xl px-3 py-2.5 text-left ${i === active ? "bg-sunken" : "hover:bg-sunken"}`;

  return (
    <div ref={box} className="relative mt-10 w-full max-w-180 text-left">
      <form action="/jobs" method="get" role="search">
        <label htmlFor={`${id}-q`} className="sr-only">
          Search jobs
        </label>
        <div className="flex flex-col gap-2.5 rounded-[1.125rem] border border-line bg-sunken p-2 sm:flex-row sm:items-center sm:pl-5">
          <div className="relative flex min-w-0 flex-1 items-center">
            <SearchIcon className="pointer-events-none absolute left-3 size-6 text-ink-faint sm:left-0" />
            <input
              id={`${id}-q`}
              type="search"
              name="q"
              role="combobox"
              aria-expanded={showing}
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={showing && active >= 0 ? optionId(active) : undefined}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOpen(true);
                setActive(-1);
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={onKeyDown}
              maxLength={100}
              placeholder="Search roles, companies or skills"
              autoComplete="off"
              className="h-12 w-full min-w-0 rounded-lg bg-transparent pr-3 pl-12 text-lg text-ink placeholder:text-ink-faint focus:outline-none focus-visible:outline-2 sm:pl-10"
            />
          </div>
          <button type="submit" className="btn btn-primary btn-lg">
            Search
          </button>
        </div>
      </form>

      <div
        id={listId}
        role="listbox"
        aria-label="Suggestions"
        hidden={!showing}
        className="absolute inset-x-0 top-full z-30 mt-2 overflow-hidden rounded-2xl border border-line bg-surface p-2 shadow-pop"
      >
        {fresh && fresh.companies.length > 0 && <p className="px-3 pt-1.5 pb-1 text-meta font-semibold text-ink-faint">Companies</p>}
        {fresh?.companies.map((c, i) => (
          <Link key={c.slug} id={optionId(i)} role="option" aria-selected={i === active} href={`/companies/${c.slug}`} className={row(i)}>
            <CompanyLogo name={c.name} domain={c.domain} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-ui font-semibold text-ink">{c.name}</span>
              <span className="block text-sm text-ink-soft">{c.open.toLocaleString("en-CA")} open tech roles</span>
            </span>
          </Link>
        ))}
        {fresh && fresh.jobs.length > 0 && <p className="px-3 pt-2 pb-1 text-meta font-semibold text-ink-faint">Jobs</p>}
        {fresh?.jobs.map((j, k) => {
          const i = fresh.companies.length + k;
          return (
            <Link key={j.id} id={optionId(i)} role="option" aria-selected={i === active} href={`/jobs/${j.id}`} className={row(i)}>
              <CompanyLogo name={j.company} domain={j.domain} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-ui font-semibold text-ink">{j.title}</span>
                <span className="block truncate text-sm text-ink-soft">
                  {j.company}
                  {j.meta && ` · ${j.meta}`}
                </span>
              </span>
            </Link>
          );
        })}
        {fresh && (
          <Link
            id={optionId(options.length - 1)}
            role="option"
            aria-selected={active === options.length - 1}
            href={all}
            className={`mt-1 flex items-center justify-between border-t border-line px-3 pt-3 pb-2 text-ui font-semibold text-accent ${
              active === options.length - 1 ? "underline" : "hover:underline"
            }`}
          >
            {fresh.companies.length + fresh.jobs.length ? `See all results for “${query}”` : `No quick matches. Search all jobs for “${query}”`}
            <ChevronRightIcon className="size-4" />
          </Link>
        )}
      </div>
    </div>
  );
}
