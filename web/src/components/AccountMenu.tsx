"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { signOut } from "@/app/actions/auth";

import { useSite } from "./SiteContext";

function initialsOf(name: string | null, email: string): string {
  const source = (name || email.split("@")[0] || "?").trim();
  const words = source.split(/[\s._-]+/).filter(Boolean);
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "?";
}

/** Signed in: an avatar menu. Signed out: sign-in and sign-up links. */
export function AccountMenu() {
  const { viewer } = useSite();
  const pathname = usePathname();

  if (!viewer) {
    const next = pathname && pathname !== "/" && !pathname.startsWith("/log") ? `?next=${encodeURIComponent(pathname)}` : "";
    return (
      <div className="hidden items-center gap-2 sm:flex">
        <Link href={`/login${next}`} className="rounded-md px-3 py-2 text-sm font-medium text-ink-soft hover:bg-sunken hover:text-ink">
          Sign in
        </Link>
        <Link href="/signup" className="inline-flex h-9 items-center rounded-lg bg-accent px-3.5 text-sm font-medium text-on-accent hover:bg-accent-hover">
          Create account
        </Link>
      </div>
    );
  }

  const item = "block w-full rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-sunken";
  return (
    <details data-popover className="group relative" key={pathname}>
      <summary className="grid size-9 place-items-center rounded-full bg-accent-tint text-sm font-semibold text-accent ring-offset-2 ring-offset-surface hover:ring-2 hover:ring-line-strong">
        <span aria-hidden="true">{initialsOf(viewer.name, viewer.email)}</span>
        <span className="sr-only">Account menu</span>
      </summary>
      <div className="absolute right-0 z-40 mt-2 w-64 rounded-xl border border-line bg-surface p-2 shadow-pop">
        <div className="border-b border-line px-3 pt-1 pb-2.5">
          <p className="truncate font-medium text-ink">{viewer.name || "Your account"}</p>
          <p className="truncate text-sm text-ink-soft">{viewer.email}</p>
        </div>
        <ul className="py-1.5">
          <li><Link href="/account" className={item}>Account</Link></li>
          <li><Link href="/resume" className={item}>My resumes and matches</Link></li>
          <li><Link href="/saved" className={item}>Saved jobs</Link></li>
          <li><Link href="/settings" className={item}>Settings</Link></li>
          {viewer.role === "admin" && <li><Link href="/admin" className={item}>Admin dashboard</Link></li>}
        </ul>
        <form action={signOut} className="border-t border-line pt-1.5">
          <button type="submit" className={item}>Sign out</button>
        </form>
      </div>
    </details>
  );
}
