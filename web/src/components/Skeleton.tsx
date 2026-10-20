import type { CSSProperties } from "react";

/*
  Loading placeholders shaped like the content they stand in for, so the
  layout doesn't jump when it arrives. Only routes that can't 404 get a
  loading boundary: one would send a 200 before notFound() could send a 404.
*/

export function Bone({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <div className={`animate-pulse rounded-md bg-sunken ${className}`} style={style} />;
}

/** Rows like a JobList's. */
export function JobRowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="grid gap-0.5">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex gap-3.5 p-4">
          <Bone className="size-11 rounded-[10px]" />
          <div className="flex-1 space-y-2.5 pt-0.5">
            <Bone className="h-4 w-3/4" />
            <Bone className="h-3 w-1/2" />
            <div className="flex gap-1.5 pt-1">
              <Bone className="h-5 w-24" />
              <Bone className="h-5 w-20 rounded-full" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
