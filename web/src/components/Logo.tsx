/** The Ghostless mark: a ghost outline struck through. */
export function GhostMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <path
        d="M5 20V10.5a7 7 0 0 1 14 0V20l-2.33-1.6L14.33 20 12 18.4 9.67 20l-2.34-1.6L5 20Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="9.5" cy="10.5" r="1.1" fill="currentColor" />
      <circle cx="14.5" cy="10.5" r="1.1" fill="currentColor" />
      <path d="M3.5 21.5 20.5 3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2 text-ink">
      <GhostMark className="size-[22px]" />
      <span className="text-lg font-bold tracking-[-0.02em]">Ghostless</span>
    </span>
  );
}
