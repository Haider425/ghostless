import { type Page, expect, test } from "@playwright/test";

/*
  End-to-end checks of the main journeys against a live API with demo data.
  They assert on structure and behaviour, not on specific demo values.
*/

const resultsCount = (page: Page) => page.getByRole("heading", { name: /^[\d,]+ (tech |software )?jobs?/ });

async function openDropdown(page: Page, label: string) {
  await page.locator("summary", { hasText: label }).first().click();
}

test("home shows a live example, live figures and one way into the jobs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("actually hiring");
  await expect(page.getByRole("region", { name: "A real posting from today's data" })).toBeVisible();
  await expect(page.getByRole("link", { name: "See this posting's full record" })).toHaveAttribute("href", /^\/jobs\/\d+$/);
  // today's figures, in the ticker (read out once, as a list)
  const figures = page.getByRole("region", { name: "Today's numbers" }).getByRole("listitem");
  await expect(figures.filter({ hasText: /^[\d,]+ open tech roles$/ })).toHaveCount(1);
  await expect(figures.filter({ hasText: /^[\d,]+ first seen this week$/ })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "What job boards don't tell you." })).toBeVisible();
  const cta = page.getByRole("link", { name: /^Search [\d,]+ open tech roles$/ });
  await expect(cta).toHaveAttribute("href", "/jobs");
  await cta.click();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(resultsCount(page)).toBeVisible();
});

test("searching from the home page lands on filtered results", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search jobs" }).fill("intern");
  await page.getByRole("button", { name: "Find real jobs", exact: true }).click();
  await expect(page).toHaveURL(/\/jobs\?q=intern/);
  await expect(page.getByRole("heading", { name: /jobs? matching/ })).toBeVisible();
  const titles = await page.getByRole("region", { name: /jobs? matching/ }).getByRole("article").getByRole("heading").allTextContents();
  expect(titles.length).toBeGreaterThan(0);
  for (const title of titles) expect(title.toLowerCase()).toContain("intern");
});

test("the home search suggests up to five matches as you type", async ({ page }) => {
  await page.goto("/");
  const box = page.getByRole("combobox", { name: "Search jobs" });
  await box.fill("intern");
  const list = page.getByRole("listbox", { name: "Suggestions" });
  await expect(list).toBeVisible();
  const options = list.getByRole("option");
  await expect(options.last()).toHaveText(/intern/i);
  // five matches at most, plus "See all results"
  expect(await options.count()).toBeLessThanOrEqual(6);
  await box.press("Escape");
  await expect(list).toBeHidden();

  // the arrow keys reach the first match and Enter opens it
  await box.press("ArrowDown");
  const first = options.first();
  const href = await first.getAttribute("href");
  await box.press("Enter");
  await expect(page).toHaveURL(new RegExp(`${href}$`));
});

test("filters update the URL and results, and clear", async ({ page }) => {
  await page.goto("/jobs");
  const count = resultsCount(page);
  const before = await count.textContent();

  await openDropdown(page, "More filters"); // ghost risk is under More filters
  await page.getByRole("checkbox", { name: "High ghost risk" }).check();
  await expect(page).toHaveURL(/risk=high/);
  await expect(count).not.toHaveText(before ?? "");
  // rows without flags show no risk tag at all, so check that every row carries the high-risk one
  const results = page.getByRole("region", { name: /jobs?/ }).getByRole("article");
  await expect(results.first()).toBeVisible();
  for (const row of await results.all()) await expect(row).toContainText("High ghost risk");
  // a checkbox dropdown stays open, so several options can be picked
  await expect(page.getByRole("checkbox", { name: "Some flags" })).toBeVisible();

  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Clear all" }).click();
  await expect(page).toHaveURL(/\/jobs$/);
  await openDropdown(page, "More filters"); // ghost risk is under More filters
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

test("coming back from an employer's site asks whether you applied, once", async ({ page, context }) => {
  // an open posting: one with an Apply link
  await page.goto("/jobs");
  const href = await page.getByRole("region", { name: /jobs?/ }).getByRole("article").first().getByRole("heading").getByRole("link").getAttribute("href");
  await page.goto(href!);
  const apply = page.getByRole("link", { name: /^Apply on .+ site/ });
  test.skip(!(await apply.count()), "this posting has closed");
  const title = (await page.getByRole("heading", { level: 1 }).textContent()) ?? "";

  // the employer's site opens in a new tab; nothing is asked yet
  await context.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) => route.fulfill({ body: "employer site" }));
  const [employer] = await Promise.all([context.waitForEvent("page"), apply.click()]);
  await employer.close();
  const prompt = page.getByRole("region", { name: "Did you apply?" });
  await expect(prompt).toBeHidden(); // back within seconds: probably didn't apply yet

  // back after a while (the visit is backdated rather than waiting)
  const comeBack = () =>
    page.evaluate(() => {
      const key = "ghostless:apply-pending:v1";
      const pending = JSON.parse(localStorage.getItem(key) ?? "null");
      if (pending) localStorage.setItem(key, JSON.stringify({ ...pending, at: Date.now() - 60_000 }));
      window.dispatchEvent(new Event("focus"));
    });
  await comeBack();
  await expect(prompt).toBeVisible();
  await expect(prompt).toContainText(title.trim());

  // "Not yet" closes it, and the same visit isn't asked about again
  await prompt.getByRole("button", { name: "Not yet" }).click();
  await expect(prompt).toBeHidden();
  await comeBack();
  await expect(prompt).toBeHidden();

  // another visit, then "Yes": signed out, the job is saved in this browser
  const [again] = await Promise.all([context.waitForEvent("page"), apply.click()]);
  await again.close();
  await comeBack();
  await prompt.getByRole("button", { name: "Yes, I applied" }).click();
  await expect(prompt).toContainText("Saved in this browser");
  await expect(page.getByRole("button", { name: /^Saved\b/ }).first()).toHaveAttribute("aria-pressed", "true");

  // a job you said you applied to is never asked about again
  const [third] = await Promise.all([context.waitForEvent("page"), apply.click()]);
  await third.close();
  await comeBack();
  await page.waitForTimeout(500);
  await expect(prompt.getByRole("button", { name: "Yes, I applied" })).toHaveCount(0);
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
