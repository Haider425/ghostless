import { type Page, expect, test } from "@playwright/test";

/*
  End-to-end checks of the main journeys against a live API with demo data.
  They assert on structure and behaviour, not on specific demo values.
*/

const resultsCount = (page: Page) => page.getByRole("heading", { name: /^[\d,]+ (tech |software )?jobs?/ });

async function openDropdown(page: Page, label: string) {
  await page.locator("summary", { hasText: label }).first().click();
}

test("home shows a live example, stats and fresh student roles", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("actually hiring");
  await expect(page.getByText("A real posting from today's data")).toBeVisible();
  await expect(page.getByText("Open tech roles")).toBeVisible();
  await expect(page.getByRole("heading", { name: "New this week for students" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Tech postings opened and closed/ })).toBeVisible();
});

test("searching from the home page lands on filtered results", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("searchbox", { name: "Search jobs" }).fill("intern");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/\/jobs\?q=intern/);
  await expect(page.getByRole("heading", { name: /jobs? matching/ })).toBeVisible();
  const titles = await page.getByRole("region", { name: /jobs? matching/ }).getByRole("article").getByRole("heading").allTextContents();
  expect(titles.length).toBeGreaterThan(0);
  for (const title of titles) expect(title.toLowerCase()).toContain("intern");
});

test("filters update the URL and results, and clear", async ({ page }) => {
  await page.goto("/jobs");
  const count = resultsCount(page);
  const before = await count.textContent();

  await openDropdown(page, "Ghost risk");
  await page.getByRole("checkbox", { name: "High ghost risk" }).check();
  await expect(page).toHaveURL(/risk=high/);
  await expect(count).not.toHaveText(before ?? "");
  const results = page.getByRole("region", { name: /jobs?/ }).getByRole("article");
  await expect(results.getByText("No flags")).toHaveCount(0);
  // a checkbox dropdown stays open, so several options can be picked
  await expect(page.getByRole("checkbox", { name: "Some flags" })).toBeVisible();

  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Clear all" }).click();
  await expect(page).toHaveURL(/\/jobs$/);
  await openDropdown(page, "Ghost risk");
  await expect(page.getByRole("checkbox", { name: "High ghost risk" })).not.toBeChecked();
});

test("the URL is clean: empty values are left out", async ({ page }) => {
  await page.goto("/jobs");
  await openDropdown(page, "Location");
  await page.getByRole("radio", { name: "Canada or remote" }).check();
  await expect(page).toHaveURL(/\/jobs\?location=canada_or_remote$/);
});

test("clicking a result opens it in the preview pane", async ({ page }) => {
  await page.goto("/jobs");
  const second = page.getByRole("region", { name: /jobs?/ }).getByRole("article").nth(1);
  const title = (await second.getByRole("heading").textContent()) ?? "";
  await second.getByRole("link").click();
  await expect(page).toHaveURL(/[?&]job=\d+/);
  await expect(page.getByRole("heading", { level: 2, name: title })).toBeVisible();
  await expect(second.getByRole("link")).toHaveAttribute("aria-current", "true");
});

test("job detail shows the posting record, evidence and links out", async ({ page }) => {
  await page.goto("/jobs?risk=medium&risk=high");
  const link = page.getByRole("region", { name: /jobs?/ }).getByRole("article").first().getByRole("link");
  const href = await link.getAttribute("href");
  await page.goto(href!);
  await expect(page).toHaveURL(/\/jobs\/\d+$/);
  const record = page.getByRole("region", { name: "Posting record" });
  await expect(record.getByRole("heading", { name: "Posting record" })).toBeVisible();
  await expect(record.getByText(/^(Open|First seen|Already up|Was open)/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "What the posting discloses" })).toBeVisible();
  const apply = page.getByRole("link", { name: /^Apply on / });
  if (await apply.count()) {
    await expect(apply).toHaveAttribute("target", "_blank");
    await expect(apply).toHaveAttribute("rel", /noopener/);
  }
});

test("a talent-pool posting quotes its own words", async ({ page }) => {
  await page.goto("/jobs?risk=high&sort=oldest");
  const links = page.getByRole("region", { name: /jobs?/ }).getByRole("article").getByRole("link");
  await links.first().waitFor();
  const hrefs = await Promise.all((await links.all()).map((l) => l.getAttribute("href")));
  for (const href of hrefs) {
    await page.goto(href!);
    const quote = page.getByRole("region", { name: "Posting record" }).locator("blockquote");
    if (await quote.count()) {
      await expect(quote.first()).toContainText("not for an existing vacancy");
      return;
    }
  }
  throw new Error("no talent-pool posting in the demo data");
});

test("unknown jobs and companies return a real 404", async ({ page }) => {
  const response = await page.goto("/jobs/999999999");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "There's nothing at this address" })).toBeVisible();
  expect((await page.goto("/companies/no-such-company"))?.status()).toBe(404);
});

test("saving a job lists it on the saved page", async ({ page }) => {
  await page.goto("/jobs");
  const first = page.getByRole("region", { name: /jobs?/ }).getByRole("article").first();
  const title = (await first.getByRole("heading").textContent()) ?? "";
  await first.getByRole("button", { name: `Save ${title}` }).click();
  await expect(first.getByRole("button", { name: `Remove ${title} from saved jobs` })).toHaveAttribute("aria-pressed", "true");

  await page.goto("/saved");
  await expect(page.getByRole("heading", { name: "1 saved job" })).toBeVisible();
  await expect(page.getByRole("link", { name: title })).toBeVisible();
  await page.getByRole("button", { name: `Remove ${title} from saved jobs` }).click();
  await expect(page.getByRole("heading", { name: "Nothing saved yet" })).toBeVisible();
});

test("skills gap marks what you have and what you're missing", async ({ page }) => {
  await page.goto("/skills");
  await page.getByLabel("Your skills").fill("Python, SQL");
  await page.getByRole("button", { name: "Compare my skills" }).click();
  await expect(page.getByRole("heading", { name: /You have \d+ of the top \d+ skills/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: "You have it" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "Missing" }).first()).toBeVisible();
});

test("companies link to their hiring record and jobs", async ({ page }) => {
  await page.goto("/companies");
  const first = page.getByRole("table").getByRole("rowheader").first().getByRole("link");
  const name = (await first.textContent()) ?? "";
  await first.click();
  await expect(page).toHaveURL(/\/companies\/[a-z0-9-]+$/);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByRole("img", { name: /Tech postings, last 12 weeks/ })).toBeVisible();

  await page.getByRole("link", { name: /^See all [\d,]+ open tech roles?$/ }).click();
  await expect(page).toHaveURL(/\/jobs\?company=/);
  for (const row of await page.getByRole("region", { name: /jobs?/ }).getByRole("article").all()) {
    await expect(row).toContainText(name);
  }
});

test("pages have one h1, a skip link, and no horizontal scroll @mobile", async ({ page }) => {
  for (const path of ["/", "/jobs", "/companies", "/companies/granite-payments", "/skills", "/calendar", "/how-it-works", "/saved"]) {
    await page.goto(path);
    await expect(page.locator("h1"), path).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeAttached();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(0);
  }
});

test("on phones, filters open as a sheet and results link to full pages @mobile", async ({ page }) => {
  test.skip(!test.info().project.name.includes("mobile"), "mobile only");
  await page.goto("/jobs");
  const level = page.getByRole("checkbox", { name: "Intern / co-op" });
  await expect(level).toBeHidden();
  await openDropdown(page, "Level");
  await expect(level).toBeVisible();
  await level.check();
  await expect(page).toHaveURL(/level=intern/);

  await page.keyboard.press("Escape");
  await page.getByRole("region", { name: /jobs?/ }).getByRole("article").first().getByRole("link").click();
  await expect(page).toHaveURL(/\/jobs\/\d+$/);
});

test("the menu opens on phones @mobile", async ({ page }) => {
  test.skip(!test.info().project.name.includes("mobile"), "mobile only");
  await page.goto("/");
  await page.locator("summary", { hasText: "Menu" }).click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Companies" }).click();
  await expect(page).toHaveURL(/\/companies$/);
});

test("search finds jobs by company name, not only by title", async ({ page }) => {
  await page.goto("/jobs?q=northwind");
  const results = page.getByRole("region", { name: /jobs/ }).or(page.locator("section[aria-labelledby=results-heading]"));
  await expect(page.locator("#results-heading")).not.toHaveText(/^0 /);
  await expect(results.getByText("Northwind Systems").first()).toBeVisible();
});
