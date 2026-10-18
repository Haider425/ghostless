/* Shown while the first search results load. Later filter changes keep the old results on screen instead. */
export default function Loading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6" aria-busy="true" aria-label="Loading jobs">
      <div className="mb-5 space-y-3">
        <div className="h-11 animate-pulse rounded-xl bg-sunken" />
        <div className="flex gap-2">
          {[5, 4.5, 5.5, 6, 6.5, 6].map((w, i) => (
            <div key={i} className="h-9 animate-pulse rounded-full bg-sunken" style={{ width: `${w}rem` }} />
          ))}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,25rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
        <div className="space-y-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex gap-3 rounded-xl border border-line bg-surface p-4">
              <div className="size-10 animate-pulse rounded-lg bg-sunken" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-3/4 animate-pulse rounded bg-sunken" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-sunken" />
                <div className="h-1.5 w-full animate-pulse rounded bg-sunken" />
              </div>
            </div>
          ))}
        </div>
        <div className="hidden h-[32rem] animate-pulse rounded-2xl border border-line bg-surface lg:block" />
      </div>
    </div>
  );
}
