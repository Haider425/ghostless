import Link from "next/link";

import { Wordmark } from "./Logo";
import { ReportDialog } from "./ReportDialog";

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="mt-24 border-t border-line bg-surface text-sm text-ink-soft">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.5fr_1fr_1fr_1fr]">
        <div className="max-w-sm space-y-3">
          <Wordmark />
          <p>
            Tech postings collected daily from employers&apos; own career sites. Every job links to the employer&apos;s original
            posting, where you apply.
          </p>
        </div>
        <div>
          <h2 className="mb-3 font-sans text-sm font-semibold text-ink">Find work</h2>
          <ul className="space-y-2">
            <li><Link href="/jobs" className="hover:text-ink hover:underline">Search jobs</Link></li>
            <li><Link href="/resume" className="hover:text-ink hover:underline">Match your resume</Link></li>
            <li><Link href="/resume/builder" className="hover:text-ink hover:underline">Resume builder</Link></li>
            <li><Link href="/companies" className="hover:text-ink hover:underline">Companies</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-3 font-sans text-sm font-semibold text-ink">Learn</h2>
          <ul className="space-y-2">
            <li><Link href="/how-it-works" className="hover:text-ink hover:underline">How the signals work</Link></li>
            <li><Link href="/skills" className="hover:text-ink hover:underline">Skills gap</Link></li>
            <li><Link href="/calendar" className="hover:text-ink hover:underline">Hiring calendar</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-3 font-sans text-sm font-semibold text-ink">Help</h2>
          <ul className="space-y-2">
            <li><ReportDialog /></li>
            <li><Link href="/settings" className="hover:text-ink hover:underline">Settings</Link></li>
            <li><Link href="/privacy" className="hover:text-ink hover:underline">Privacy</Link></li>
            <li><Link href="/terms" className="hover:text-ink hover:underline">Terms</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-7xl px-4 py-5 text-xs text-ink-faint sm:px-6">
          © {year} Ghostless. Not affiliated with the employers listed. Job details belong to the employers that posted them.
        </p>
      </div>
    </footer>
  );
}
