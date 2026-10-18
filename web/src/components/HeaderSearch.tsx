"use client";

import { usePathname, useSearchParams } from "next/navigation";

import { SearchIcon } from "./Icons";

/** Title search in the header, except on home and jobs, which have their own. */
export function HeaderSearch() {
  const pathname = usePathname();
  const params = useSearchParams();
  if (pathname === "/" || pathname === "/jobs") return <div className="hidden flex-1 md:block" />;
  return (
    <form action="/jobs" method="get" role="search" className="hidden min-w-0 flex-1 md:block md:max-w-xs">
      <label htmlFor="header-q" className="sr-only">
        Search jobs
      </label>
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint" />
        <input
          id="header-q"
          type="search"
          name="q"
          defaultValue={params.get("q") ?? ""}
          maxLength={100}
          placeholder="Search jobs, companies, skills"
          autoComplete="off"
          className="field h-8 border-line bg-sunken/60 pl-9 text-sm focus:bg-surface"
        />
      </div>
    </form>
  );
}
