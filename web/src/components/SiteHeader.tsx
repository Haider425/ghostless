import Link from "next/link";
import { Suspense } from "react";

import { AccountMenu } from "./AccountMenu";
import { HeaderSearch } from "./HeaderSearch";
import { Wordmark } from "./Logo";
import { MobileNav, NavLinks, SavedLink } from "./NavLinks";
import { PopoverManager } from "./PopoverManager";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur-md supports-[backdrop-filter]:bg-paper/75">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2 focus:text-ink"
      >
        Skip to content
      </a>
      <div className="relative mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:px-6 lg:gap-5">
        <Link href="/" aria-label="Ghostless home" className="shrink-0 rounded-md py-1">
          <Wordmark />
        </Link>
        <NavLinks />
        <Suspense fallback={<div className="hidden flex-1 md:block" />}>
          <HeaderSearch />
        </Suspense>
        <div className="ml-auto flex items-center gap-1">
          <SavedLink className="hidden sm:inline-flex" />
          <AccountMenu />
          <MobileNav />
        </div>
      </div>
      <PopoverManager />
    </header>
  );
}
