import { Bone, JobRowsSkeleton } from "@/components/Skeleton";

/* Shown while the first search results load. Later filter changes keep the old results on screen instead. */
export default function Loading() {
  return (
    <div className="px-4 pt-6 pb-16 sm:px-6 lg:px-10 lg:pt-7" aria-busy="true" aria-label="Loading jobs">
      <div className="flex flex-wrap gap-2.5">
        <Bone className="h-12 w-full rounded-xl lg:w-104" />
        {[6.5, 7, 7.5, 9].map((w, i) => (
          <Bone key={i} className="h-10 rounded-full" style={{ width: `${w}rem` }} />
        ))}
      </div>
      <Bone className="mt-6 h-6 w-2/3" />
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,32rem)_minmax(0,1fr)]">
        <div>
          <Bone className="mb-3 h-5 w-36" />
          <JobRowsSkeleton />
        </div>
        <div className="panel hidden h-[36rem] animate-pulse lg:block" />
      </div>
    </div>
  );
}
