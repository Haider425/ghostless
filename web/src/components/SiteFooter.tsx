import Link from "next/link";

import { ReportDialog } from "./ReportDialog";

/** One quiet line at the end of every page; the navigation is in the header. */
export function SiteFooter() {
  const year = new Date().getFullYear();
  const link = "hover:text-ink";
  return (
    <footer className="border-t border-line text-sm text-ink-soft">
      <div className="flex flex-wrap items-center gap-x-7 gap-y-3 px-4 py-7 sm:px-6 lg:px-10">
        <p className="mr-auto text-ink-faint">
          © {year} Ghostless. Not affiliated with the employers listed. Every job links to the employer&apos;s own posting.
        </p>
        <ul className="flex flex-wrap gap-x-7 gap-y-2 font-medium">
          <li><Link href="/how-it-works" className={link}>How it works</Link></li>
          <li><Link href="/settings" className={link}>Settings</Link></li>
          <li><Link href="/privacy" className={link}>Privacy</Link></li>
          <li><Link href="/terms" className={link}>Terms</Link></li>
          <li><ReportDialog className={`${link} font-medium`} /></li>
        </ul>
      </div>
    </footer>
  );
}
