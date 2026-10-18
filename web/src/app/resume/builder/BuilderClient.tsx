"use client";

import dynamic from "next/dynamic";

/*
  The builder reads and writes drafts in browser storage and prints through a
  portal on <body>, so it renders only in the browser.
*/
export const BuilderClient = dynamic(() => import("./Builder").then((m) => m.Builder), {
  ssr: false,
  loading: () => (
    <div aria-busy="true" className="grid gap-6 lg:grid-cols-2">
      <div className="h-[32rem] animate-pulse rounded-2xl border border-line bg-surface" />
      <div className="hidden h-[32rem] animate-pulse rounded-2xl border border-line bg-surface lg:block" />
    </div>
  ),
});
