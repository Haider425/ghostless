import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { LEVEL_LABELS, shortLocation } from "@/lib/format";
import { respond } from "@/lib/route";

const LIMIT = 5;
const MAX_COMPANIES = 2;

/**
 * Suggestions for the home page's search box: up to five results in all,
 * companies whose name matches first (the ones with the most open tech roles),
 * then open jobs. The API picks the companies, so only those two are read.
 */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim().slice(0, 100) ?? "";
  if (q.length < 2) return NextResponse.json({ companies: [], jobs: [] });
  return respond(async () => {
    // hiring companies whose name contains the query: names that start with it first, then the ones hiring the most
    const [companies, jobs] = await Promise.all([api.companyNames({ q, limit: MAX_COMPANIES }), api.jobs({ q, limit: LIMIT })]);
    const named = companies.map((c) => ({ name: c.name, slug: c.slug, domain: c.domain, open: c.tech_active_jobs }));
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
