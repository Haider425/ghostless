"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { startingJobsHref } from "@/lib/nav";
import { useSavedJobs } from "@/lib/saved";

import { BookmarkIcon, ChevronDownIcon } from "./Icons";
import { useSite } from "./SiteContext";

const INSIGHTS = [
  { href: "/companies", label: "Companies", note: "Who's hiring, how fast they fill roles" },
  { href: "/skills", label: "Skills gap", note: "What postings ask for, and what you're missing" },
  { href: "/calendar", label: "Hiring calendar", note: "When internships and new grad roles open" },
  { href: "/how-it-works", label: "How it works", note: "Where the data comes from and what flags mean" },
];

export function isCurrent(pathname: string, href: string) {
  const path = href.split("?")[0]!;
  return pathname === path || pathname.startsWith(`${path}/`);
}

const linkClass =
  "block rounded-md px-2.5 py-1.5 font-medium text-ink-soft transition-colors hover:bg-sunken hover:text-ink aria-[current=page]:bg-sunken aria-[current=page]:text-ink";

/** Desktop navigation. */
export function NavLinks() {
  const pathname = usePathname();
  const { prefs } = useSite();
  const jobs = startingJobsHref(prefs);
  const insightsActive = INSIGHTS.some((i) => isCurrent(pathname, i.href));
  return (
    <nav aria-label="Main" className="hidden lg:block">
      <ul className="flex items-center gap-1 text-sm whitespace-nowrap">
        <li>
          <Link href={jobs} aria-current={isCurrent(pathname, "/jobs") ? "page" : undefined} className={linkClass}>
            Jobs
          </Link>
        </li>
        <li>
          <Link href="/resume" aria-current={isCurrent(pathname, "/resume") ? "page" : undefined} className={linkClass}>
            Resume
          </Link>
        </li>
        <li>
          <details data-popover className="group relative">
            <summary className={`${linkClass} inline-flex items-center gap-1 group-open:bg-sunken ${insightsActive ? "bg-sunken text-ink" : ""}`}>
              Insights
              <ChevronDownIcon className="size-3.5 opacity-70 transition-transform group-open:rotate-180" />
            </summary>
            <ul className="absolute left-0 z-40 mt-1.5 w-72 rounded-xl border border-line bg-surface p-1.5 shadow-pop">
              {INSIGHTS.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isCurrent(pathname, item.href) ? "page" : undefined}
                    className="block rounded-lg px-2.5 py-2 whitespace-normal hover:bg-sunken aria-[current=page]:bg-sunken"
                  >
                    <span className="block font-medium text-ink">{item.label}</span>
                    <span className="block text-xs text-ink-faint">{item.note}</span>
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

/** The saved jobs link with its count. */
export function SavedLink({ className = "" }: { className?: string }) {
  const pathname = usePathname();
  const { count } = useSavedJobs();
  return (
    <Link
      href="/saved"
      aria-current={isCurrent(pathname, "/saved") ? "page" : undefined}
      className={`inline-flex h-8 items-center gap-2 rounded-md px-2.5 text-sm font-medium text-ink-soft transition-colors hover:bg-sunken hover:text-ink aria-[current=page]:bg-sunken aria-[current=page]:text-ink ${className}`}
    >
      <BookmarkIcon className="size-4" filled={count > 0} />
      <span>Saved</span>
      {count > 0 && (
        <span className="min-w-5 rounded-full bg-accent-tint px-1.5 text-center text-xs leading-5 font-semibold text-accent tabular-nums">
          {count}
          <span className="sr-only"> jobs</span>
        </span>
      )}
    </Link>
  );
}

/** Phone and tablet navigation: a disclosure, so it works without JavaScript. */
export function MobileNav() {
  const pathname = usePathname();
  const { prefs, viewer } = useSite();
  const links = [
    { href: startingJobsHref(prefs), label: "Jobs" },
    { href: "/resume", label: "Resume and matches" },
    { href: "/resume/builder", label: "Resume builder" },
    ...INSIGHTS,
    { href: "/saved", label: "Saved jobs" },
    { href: "/settings", label: "Settings" },
    ...(viewer ? [{ href: "/account", label: "Account" }] : []),
    ...(viewer?.role === "admin" ? [{ href: "/admin", label: "Admin dashboard" }] : []),
  ];
  return (
    <details className="group lg:hidden" key={pathname /* closes after navigating */}>
      <summary className="grid size-9 place-items-center rounded-md text-ink hover:bg-sunken">
        <span className="sr-only">Menu</span>
        <svg viewBox="0 0 20 20" className="size-5 group-open:hidden" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
          <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
        </svg>
        <svg viewBox="0 0 20 20" className="hidden size-5 group-open:block" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
          <path d="m5 5 10 10M15 5 5 15" />
        </svg>
      </summary>
      <nav aria-label="Main" className="absolute inset-x-0 top-full z-40 border-b border-line bg-surface px-4 pb-4 shadow-pop">
        <ul className="grid gap-0.5 pt-2">
          {links.map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                aria-current={isCurrent(pathname, href) ? "page" : undefined}
                className="block rounded-md px-3 py-2.5 text-ink-soft hover:bg-sunken hover:text-ink aria-[current=page]:bg-accent-tint aria-[current=page]:text-accent"
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
        {!viewer && (
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3">
            <Link href="/login" className="inline-flex h-10 items-center justify-center rounded-lg border border-line-strong font-medium text-ink">
              Sign in
            </Link>
            <Link href="/signup" className="btn btn-primary">
              Create account
            </Link>
          </div>
        )}
      </nav>
    </details>
  );
}
