import { expect, test } from "@playwright/test";

import { EMPTY_FILTERS, activeFilterCount, jobsHref, parseFilters, toApiQuery } from "../src/lib/filters";
import { ago, formatDate, formatSalary, initials, possessive, shortLocation } from "../src/lib/format";

/* Pure-function tests: no browser, no server. */

test.describe("filters", () => {
  test("parses repeated and single params", () => {
    const f = parseFilters({ level: ["intern", "new_grad"], role: "sde", q: " data ", page: "3", new: "7" });
    expect(f.level).toEqual(["intern", "new_grad"]);
    expect(f.role).toBe("sde");
    expect(f.q).toBe("data");
    expect(f.page).toBe(3);
    expect(f.newWithinDays).toBe(7);
  });

  test("drops invalid values instead of failing", () => {
    const f = parseFilters({ level: ["wizard", "intern", "intern"], location: "mars", sort: "random", page: "-4", new: "5" });
    expect(f.level).toEqual(["intern"]);
    expect(f.location).toBe("any");
    expect(f.sort).toBe("newest");
    expect(f.page).toBe(1);
    expect(f.newWithinDays).toBeNull();
    expect(parseFilters({ page: "999999" }).page).toBe(400);
  });

  test("round-trips through a URL", () => {
    const f = parseFilters({ q: "data", level: ["intern"], risk: "low", location: "canada", salary: "1", page: "2" });
    const href = jobsHref(f);
    const params = Object.fromEntries(
      [...new URL(href, "http://x").searchParams.keys()].map((k) => [k, new URL(href, "http://x").searchParams.getAll(k)]),
    );
    expect(parseFilters(params)).toEqual(f);
  });

  test("omits defaults from URLs", () => {
    expect(jobsHref(EMPTY_FILTERS)).toBe("/jobs");
    expect(jobsHref(EMPTY_FILTERS, { page: 1, sort: "newest", location: "any" })).toBe("/jobs");
  });

  test("builds the API query with paging", () => {
    const query = toApiQuery(parseFilters({ page: "3", risk: ["low", "medium"] }));
    expect(query.offset).toBe(50);
    expect(query.limit).toBe(25);
    expect(query.risk).toEqual(["low", "medium"]);
    expect(query.level).toBeUndefined();
  });

  test("searches every tech role unless one is chosen", () => {
    expect(toApiQuery(EMPTY_FILTERS).role).toEqual(["sde", "data_eng", "data", "ml", "hardware", "security"]);
    expect(toApiQuery(parseFilters({ role: "hardware" })).role).toEqual(["hardware"]);
    expect(toApiQuery(parseFilters({ role: "all" })).role).toBeUndefined(); // every posting, tech or not
    expect(parseFilters({ role: "wizard" }).role).toBe("tech"); // unknown values fall back
  });

  test("keeps the selected job only while the search is unchanged", () => {
    const f = parseFilters({ q: "data", job: "42" });
    expect(f.selected).toBe(42);
    expect(jobsHref(f)).toBe("/jobs?q=data&job=42");
    expect(jobsHref(f, { selected: 7 })).toBe("/jobs?q=data&job=7");
    expect(jobsHref(f, { page: 2 })).toBe("/jobs?q=data&page=2");
    expect(parseFilters({ job: "abc" }).selected).toBeNull();
  });

  test("counts active filters", () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
    expect(activeFilterCount(parseFilters({ level: ["intern", "new_grad"], salary: "1", location: "remote" }))).toBe(4);
  });
});

test.describe("format", () => {
  test("salaries", () => {
    expect(formatSalary({ min: 90000, max: 110000, period: "year", currency: "CAD" })).toBe("$90k to $110k a year CAD");
    expect(formatSalary({ min: 25.5, max: 32, period: "hour", currency: null })).toBe("$25.50 to $32.00 an hour");
    expect(formatSalary({ min: 30, max: 30, period: "hour", currency: "CAD" })).toBe("$30 an hour CAD");
    expect(formatSalary({ min: 96900, max: 145300, period: "year", currency: "GBP" })).toBe("£97k to £145k a year");
    expect(formatSalary({ min: 43600, max: 65400, period: "year", currency: "EUR" })).toBe("€44k to €65k a year");
  });

  test("relative ages", () => {
    const now = new Date("2026-10-17T12:00:00Z");
    expect(ago("2026-10-17T01:00:00Z", now)).toBe("today");
    expect(ago("2026-10-16T11:00:00Z", now)).toBe("yesterday");
    expect(ago("2026-10-07T12:00:00Z", now)).toBe("10 days ago");
    expect(ago("2026-08-17T12:00:00Z", now)).toBe("about 2 months ago");
  });

  test("dates use Toronto time, not the server's", () => {
    // 02:00 UTC on Oct 18 is still the evening of Oct 17 in Toronto
    expect(formatDate("2026-10-18T02:00:00Z")).toBe("Oct 17, 2026");
  });

  test("possessives", () => {
    expect(possessive("Stripe")).toBe("Stripe's");
    expect(possessive("Granite Payments")).toBe("Granite Payments'");
  });
});

test.describe("labels", () => {
  test("short locations and initials", () => {
    expect(shortLocation("Toronto, ON | Montreal, QC | Remote")).toBe("Toronto, ON +2 more");
    expect(shortLocation(null)).toBe("Location not listed");
    expect(initials("Granite Payments")).toBe("GP");
    expect(initials("stripe")).toBe("St");
  });
});
