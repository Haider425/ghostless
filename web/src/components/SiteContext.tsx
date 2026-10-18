"use client";

import { type ReactNode, createContext, useContext } from "react";

import type { Prefs } from "@/lib/prefs";

/*
  What client components need to know about the visitor: whether they're
  signed in, and their display preferences. Provided once by the root layout.
*/

export interface Viewer {
  id: number;
  name: string | null;
  email: string;
  role: "user" | "admin";
  emailVerified: boolean;
}

interface Site {
  viewer: Viewer | null;
  prefs: Prefs;
  aiEnabled: boolean;
}

const SiteContext = createContext<Site | null>(null);

export function SiteProvider({ value, children }: { value: Site; children: ReactNode }) {
  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}

export function useSite(): Site {
  const site = useContext(SiteContext);
  if (!site) throw new Error("useSite must be used inside SiteProvider");
  return site;
}
