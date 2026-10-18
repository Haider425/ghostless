import { Bone, JobRowsSkeleton } from "@/components/Skeleton";

/* Shown while the first search results load. Later filter changes keep the old results on screen instead. */
export default function Loading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6" aria-busy="true" aria-label="Loading jobs">
      <div className="mb-5 space-y-3">
        <Bone className="h-10 rounded-lg" />
        <div className="flex gap-1.5">
          {[4.5, 5, 5.5, 6, 6, 6.5].map((w, i) => (
            <Bone key={i} className="h-8 rounded-lg" style={{ width: `${w}rem` }} />
          ))}
        </div>
        <Bone className="h-9" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,25rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
        <div>
          <Bone className="mb-3 h-5 w-32" />
          <JobRowsSkeleton />
        </div>
        <div className="panel hidden h-[32rem] animate-pulse lg:block" />
      </div>
    </div>
  );
}
