import type { MetadataRoute } from "next";

import { api } from "@/lib/api";

const site = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

/*
  Pages for search engines: the main pages, every company page, and the most
  recent open jobs (sitemaps are capped at 50,000 entries). Regenerated hourly.
*/
export const revalidate = 3600;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const fixed = ["", "/jobs", "/companies", "/skills", "/calendar", "/resume", "/resume/builder", "/how-it-works", "/privacy", "/terms"].map(
    (path) => ({ url: `${site}${path}`, changeFrequency: "daily" as const, priority: path === "" ? 1 : 0.7 }),
  );
  try {
    const [companies, jobs] = await Promise.all([api.companyNames(), api.jobs({ limit: 100, sort: "newest" })]);
    return [
      ...fixed,
      ...companies.map((c) => ({ url: `${site}/companies/${c.slug}`, changeFrequency: "daily" as const, priority: 0.6 })),
      ...jobs.items.map((j) => ({ url: `${site}/jobs/${j.id}`, lastModified: j.first_seen, changeFrequency: "weekly" as const, priority: 0.5 })),
    ];
  } catch {
    return fixed; // the API being down shouldn't break the sitemap
  }
}
