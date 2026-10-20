import Link from "next/link";

import { AccountMenu } from "./AccountMenu";
import { Wordmark } from "./Logo";
import { MobileNav, NavLinks, SavedLink } from "./NavLinks";
import { PopoverManager } from "./PopoverManager";

/* A solid bar (no backdrop blur): blur would trap the phone menu, which is fixed-position, inside the bar. */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-ink focus:shadow-pop"
      >
        Skip to content
      </a>
      <div className="flex h-(--header-h) items-center gap-10 px-4 sm:px-6 lg:px-10">
        <Link href="/" aria-label="Ghostless home" className="shrink-0 rounded-md py-1">
          <Wordmark />
        </Link>
        <NavLinks />
        <div className="ml-auto flex items-center gap-3">
          <SavedLink className="hidden sm:inline-flex" />
          <AccountMenu />
          <MobileNav />
        </div>
      </div>
      <PopoverManager />
    </header>
  );
}
