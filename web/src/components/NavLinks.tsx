"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, SVGProps } from "react";

import { startingJobsHref } from "@/lib/nav";
import { useSavedJobs } from "@/lib/saved";

import { BookmarkIcon, CalendarIcon, ChartIcon, ChevronDownIcon, ChevronRightIcon, CloseIcon, InfoIcon, MenuIcon } from "./Icons";
import { useSite } from "./SiteContext";

const INSIGHTS: { href: string; label: string; note: string; icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { href: "/skills", label: "Skills gap", note: "What postings ask for, and what you're missing", icon: ChartIcon },
  { href: "/calendar", label: "Hiring calendar", note: "When internships and new grad roles open", icon: CalendarIcon },
  { href: "/how-it-works", label: "How it works", note: "Where the data comes from and what flags mean", icon: InfoIcon },
];

export function isCurrent(pathname: string, href: string) {
  const path = href.split("?")[0]!;
  return pathname === path || pathname.startsWith(`${path}/`);
}

const linkClass =
  "block rounded-lg px-1 py-1.5 text-ui font-medium text-ink-soft transition-colors hover:text-ink aria-[current=page]:font-semibold aria-[current=page]:text-ink";

/** Desktop navigation: Jobs, Companies, Resume, and the Insights menu. */
export function NavLinks() {
  const pathname = usePathname();
  const { prefs } = useSite();
  const jobs = startingJobsHref(prefs);
  const insightsActive = INSIGHTS.some((i) => isCurrent(pathname, i.href));
  return (
    <nav aria-label="Main" className="hidden lg:block">
      <ul className="flex items-center gap-7 whitespace-nowrap">
        {[
          { href: jobs, label: "Jobs", match: "/jobs" },
          { href: "/companies", label: "Companies", match: "/companies" },
          { href: "/resume", label: "Resume", match: "/resume" },
        ].map(({ href, label, match }) => (
          <li key={label}>
            <Link href={href} aria-current={isCurrent(pathname, match) ? "page" : undefined} className={linkClass}>
              {label}
            </Link>
          </li>
        ))}
        <li>
          <details data-popover className="group relative">
            <summary className={`${linkClass} inline-flex items-center gap-1 ${insightsActive ? "font-semibold text-ink" : ""}`}>
              Insights
              <ChevronDownIcon className="size-3.5 opacity-60 transition-transform group-open:rotate-180" />
            </summary>
            <ul className="absolute left-1/2 z-40 mt-2 w-80 -translate-x-1/2 rounded-2xl border border-line bg-surface p-2 shadow-pop">
              {INSIGHTS.map(({ href, label, note, icon: Icon }) => (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={isCurrent(pathname, href) ? "page" : undefined}
                    className="flex gap-3 rounded-xl px-3 py-2.5 whitespace-normal hover:bg-sunken aria-[current=page]:bg-sunken"
                  >
                    <Icon className="mt-0.5 size-[18px] shrink-0 text-ink" />
                    <span>
                      <span className="block text-ui font-semibold text-ink">{label}</span>
                      <span className="block text-sm text-ink-soft">{note}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        </li>
      </ul>
    </nav>
  );
}

/** Saved jobs, with their count. Signed in, the same page is the application tracker. */
export function SavedLink({ className = "" }: { className?: string }) {
  const pathname = usePathname();
  const { viewer } = useSite();
  const { count } = useSavedJobs();
  return (
    <Link
      href="/saved"
      aria-current={isCurrent(pathname, "/saved") ? "page" : undefined}
      className={`inline-flex h-10 items-center gap-2 rounded-lg px-2 text-ui font-medium text-ink-soft transition-colors hover:text-ink aria-[current=page]:font-semibold aria-[current=page]:text-ink ${className}`}
    >
      <BookmarkIcon className="size-[18px]" filled={count > 0} />
      <span>{viewer ? "Applications" : "Saved"}</span>
      {count > 0 && (
        <span className="min-w-5 rounded-full bg-accent-tint px-1.5 text-center text-xs leading-5 font-semibold text-accent tabular-nums">
          {count}
          <span className="sr-only"> jobs</span>
        </span>
      )}
    </Link>
  );
}

/** Phones and tablets: a full-width menu under the bar. A disclosure, so it works without JavaScript. */
export function MobileNav() {
  const pathname = usePathname();
  const { prefs, viewer } = useSite();
  const main = [
    { href: startingJobsHref(prefs), label: "Jobs", match: "/jobs" },
    { href: "/companies", label: "Companies", match: "/companies" },
    { href: "/resume", label: "Resume", match: "/resume" },
    { href: "/saved", label: viewer ? "Applications" : "Saved jobs", match: "/saved" },
  ];
  const account = [
    { href: "/settings", label: "Settings" },
    ...(viewer ? [{ href: "/account", label: "Account" }] : []),
    ...(viewer?.role === "admin" ? [{ href: "/admin", label: "Admin dashboard" }] : []),
  ];
  const big =
    "flex items-center justify-between rounded-xl px-3 py-3.5 text-lg font-semibold text-ink hover:bg-sunken aria-[current=page]:bg-sunken";
  const small = "block rounded-xl px-3 py-3 text-base font-medium text-ink-soft hover:bg-sunken hover:text-ink aria-[current=page]:text-ink";
  return (
    <details className="group lg:hidden" key={pathname /* closes after navigating */}>
      <summary className="grid size-10 place-items-center rounded-lg text-ink hover:bg-sunken">
        <span className="sr-only">Menu</span>
        <MenuIcon className="size-6 group-open:hidden" />
        <CloseIcon className="hidden size-6 group-open:block" />
      </summary>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 top-(--header-h) bottom-0 z-40 overflow-y-auto border-t border-line bg-paper px-4 pt-3 pb-8"
      >
        <ul className="grid gap-0.5">
          {main.map(({ href, label, match }) => (
            <li key={label}>
              <Link href={href} aria-current={isCurrent(pathname, match) ? "page" : undefined} className={big}>
                {label}
                <ChevronRightIcon className="size-[18px] text-ink-faint" />
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-5 px-3 text-meta font-semibold text-ink-faint">Insights</p>
        <ul className="mt-1 grid gap-0.5">
          {INSIGHTS.map(({ href, label }) => (
            <li key={href}>
              <Link href={href} aria-current={isCurrent(pathname, href) ? "page" : undefined} className={small}>
                {label}
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-5 px-3 text-meta font-semibold text-ink-faint">Account</p>
        <ul className="mt-1 grid gap-0.5">
          {account.map(({ href, label }) => (
            <li key={href}>
              <Link href={href} aria-current={isCurrent(pathname, href) ? "page" : undefined} className={small}>
                {label}
              </Link>
            </li>
          ))}
        </ul>
        {!viewer && (
          <div className="mt-6 grid grid-cols-2 gap-2.5">
            <Link href="/login" className="btn btn-secondary btn-lg">
              Log in
            </Link>
            <Link href="/signup" className="btn btn-primary btn-lg">
              Sign up
            </Link>
          </div>
        )}
      </nav>
    </details>
  );
}
