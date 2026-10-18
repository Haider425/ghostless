import { EMPTY_FILTERS, jobsHref } from "./filters";
import type { Prefs } from "./prefs";

/** Where "Jobs" links go: the search, starting from the visitor's preferred location and risk. */
export function startingJobsHref(prefs: Pick<Prefs, "default_location" | "hide_high_risk">): string {
  return jobsHref({
    ...EMPTY_FILTERS,
    location: prefs.default_location,
    risk: prefs.hide_high_risk ? ["low", "medium"] : [],
  });
}
