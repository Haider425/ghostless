import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { LEVEL_LABELS, shortLocation } from "@/lib/format";
import { respond } from "@/lib/route";

const LIMIT = 5;
const MAX_COMPANIES = 2;

/**
 * Suggestions for the home page's search box: up to five results in all,
 * companies whose name matches first (the ones with the most open tech roles),
 * then open jobs. Both lists come from the same cached API calls as the
 * Companies and Jobs pages.
 */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim().slice(0, 100) ?? "";
  if (q.length < 2) return NextResponse.json({ companies: [], jobs: [] });
  return respond(async () => {
    const needle = q.toLowerCase();
    const [companies, jobs] = await Promise.all([api.companies(), api.jobs({ q, limit: LIMIT })]);
    const named = companies
      .filter((c) => c.tech_active_jobs > 0 && c.name.toLowerCase().includes(needle))
      // names that start with the query first, then the ones hiring the most
      .sort((a, b) => Number(b.name.toLowerCase().startsWith(needle)) - Number(a.name.toLowerCase().startsWith(needle)) || b.tech_active_jobs - a.tech_active_jobs)
      .slice(0, MAX_COMPANIES)
      .map((c) => ({ name: c.name, slug: c.slug, domain: c.domain, open: c.tech_active_jobs }));
    return {
      companies: named,
      jobs: jobs.items.slice(0, LIMIT - named.length).map((j) => ({
        id: j.id,
        title: j.title,
        company: j.company,
        domain: j.company_domain ?? null,
        meta: [shortLocation(j.location), LEVEL_LABELS[j.level]].filter(Boolean).join(" · "),
      })),
    };
  });
}
