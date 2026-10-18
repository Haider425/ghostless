import Link from "next/link";

import { type JobFilters, ROLE_SCOPES, type RoleScope, jobsHref } from "@/lib/filters";
import { ROLE_TABS } from "@/lib/format";

const LABELS: Record<RoleScope, string> = {
  tech: "All tech",
  ...(ROLE_TABS as Record<Exclude<RoleScope, "tech" | "all">, string>),
  all: "All jobs",
};

/**
 * Role as a row of tabs: one choice, always visible. "All tech" is the
 * default; "All jobs" adds non-tech roles at the same employers.
 * Plain links, so they work without JavaScript and can be shared.
 */
export function RoleTabs({ filters }: { filters: JobFilters }) {
  return (
    <nav aria-label="Role" className="scroll-quiet -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex min-w-max gap-1 border-b border-line">
        {ROLE_SCOPES.map((scope) => {
          const current = filters.role === scope;
          return (
            <li key={scope}>
              <Link
                href={jobsHref(filters, { role: scope, page: 1 })}
                aria-current={current ? "page" : undefined}
                scroll={false}
                className="-mb-px inline-block border-b-2 border-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap text-ink-soft transition-colors hover:text-ink aria-[current=page]:border-accent aria-[current=page]:text-accent"
              >
                {LABELS[scope]}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
