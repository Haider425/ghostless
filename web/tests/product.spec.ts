import { type Page, expect, test } from "@playwright/test";
import path from "node:path";

/*
  Accounts, settings, resume matching, the application tracker, problem
  reports and admin access. Each test signs up a fresh account, so tests are
  independent of each other and of what's already in the database.
*/

const PASSWORD = "correct horse battery staple";
const RESUME = path.join(process.cwd(), "tests", "fixtures", "resume.docx");

// Each test is its own visitor: sign-ups are rate limited per IP address, and
// the website forwards the visitor's address to the API (see lib/session.ts).
test.beforeEach(async ({ page }) => {
  const octet = () => Math.floor(Math.random() * 250) + 1;
  await page.setExtraHTTPHeaders({ "x-forwarded-for": `10.${octet()}.${octet()}.${octet()}` });
});

/** Open a page and wait until its scripts are running, so clicks reach React. */
async function go(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
}

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

async function signUp(page: Page, label = "test") {
  const email = uniqueEmail(label);
  await go(page, "/signup");
  await page.getByLabel("Name", { exact: true }).fill("Test User");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox", { name: /I agree/ }).check();
  await page.getByRole("main").getByRole("button", { name: /create account/i }).click();
  await expect(page).not.toHaveURL(/\/signup/);
  return email;
}

test("sign up, sign out and sign back in", async ({ page }) => {
  const email = await signUp(page, "auth");
  await page.locator("summary", { hasText: "Account menu" }).click();
  await page.locator("details[open]").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();

  await go(page, "/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("wrong password entirely");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(/don.t match/);

  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.locator("summary", { hasText: "Account menu" })).toBeVisible();
});

test("settings change the theme and text size, and survive a reload", async ({ page }) => {
  await go(page, "/settings");
  await page.getByText("Dark", { exact: true }).click();
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/settings") && r.ok());
  await page.getByText("Large", { exact: true }).click();
  await saved;
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-text", "lg");
  await page.reload();
  // applied by the server, so there's no flash of the wrong theme
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-text", "lg");
});

test("a resume gets a strength report, then match scores on jobs", async ({ page }) => {
  await go(page, "/resume");
  await page.getByLabel("Resume file").setInputFiles(RESUME);
  await expect(page.getByText(/Resume strength/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Python", { exact: true }).first()).toBeVisible();

  await go(page, "/jobs");
  await expect(page.getByText(/\d+% match/).first()).toBeVisible({ timeout: 15000 });

  await go(page, "/resume/matches");
  await expect(page.getByText(/Best of [\d,]+ open tech jobs/)).toBeVisible({ timeout: 15000 });
});

test("saved jobs become a tracker with statuses and notes when signed in", async ({ page }) => {
  await signUp(page, "tracker");
  await go(page, "/jobs");
  const first = page.getByRole("region", { name: /jobs?/ }).getByRole("article").first();
  const title = (await first.getByRole("heading").textContent()) ?? "";
  await first.getByRole("button", { name: `Save ${title}` }).click();
  await expect(first.getByRole("button", { name: `Remove ${title} from saved jobs` })).toBeVisible();

  await go(page, "/saved");
  await expect(page.getByRole("heading", { name: "Applications" })).toBeVisible();
  await page.getByLabel(`Status for ${title}`).selectOption("applied");
  await page.getByText("Add notes").click();
  await page.getByLabel(`Notes for ${title}`).fill("Referred by a friend");
  await page.getByRole("heading", { name: "Applications" }).click(); // blur saves the notes
  await page.waitForTimeout(500);

  await page.reload();
  await expect(page.getByLabel(`Status for ${title}`)).toHaveValue("applied");
  await expect(page.getByLabel(`Notes for ${title}`)).toHaveValue("Referred by a friend");
  await page.getByRole("tab", { name: /Applied/ }).click();
  await expect(page.getByRole("link", { name: title })).toBeVisible();
});

test("anyone can report a problem with a job", async ({ page }) => {
  await go(page, "/jobs?risk=high");
  const href = await page.getByRole("region", { name: /jobs?/ }).getByRole("article").first().getByRole("link").getAttribute("href");
  await go(page, href!);
  await page.getByRole("button", { name: "Report it" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Details").fill("The posting has already been filled.");
  await dialog.getByRole("button", { name: /send/i }).click();
  await expect(dialog).toContainText(/thank/i);
});

test("the admin dashboard is hidden from everyone but admins", async ({ page }) => {
  expect((await page.goto("/admin"))?.status()).toBe(404);
  await signUp(page, "notadmin");
  expect((await page.goto("/admin"))?.status()).toBe(404);
});

test("privacy, terms, robots and sitemap are published", async ({ page, request }) => {
  await go(page, "/privacy");
  await expect(page.getByRole("heading", { level: 1, name: "Privacy policy" })).toBeVisible();
  await go(page, "/terms");
  await expect(page.getByRole("heading", { level: 1, name: "Terms of use" })).toBeVisible();
  const robots = await (await request.get("/robots.txt")).text();
  expect(robots).toContain("Disallow: /admin");
  const sitemap = await (await request.get("/sitemap.xml")).text();
  expect(sitemap).toContain("/companies/");
});

test("deleting an account signs you out for good", async ({ page }) => {
  const email = await signUp(page, "delete");
  await go(page, "/account");
  await page.getByText("I want to delete my account").click();
  await page.getByLabel("Your password").fill(PASSWORD);
  await page.getByLabel(/to confirm/).fill("delete my account");
  await page.getByRole("button", { name: "Delete my account" }).click();
  await expect(page).toHaveURL(/\/$|\/\?/);
  await go(page, "/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
});

test.describe("Google and GitHub sign-in", () => {
  // The providers themselves are never contacted: requests to them are intercepted.
  async function startGoogle(page: Page): Promise<URL> {
    let target: URL | null = null;
    await page.route("https://accounts.google.com/**", (route) => {
      target = new URL(route.request().url());
      return route.fulfill({ status: 200, contentType: "text/html", body: "<p>Google sign-in (test)</p>" });
    });
    await go(page, "/login");
    const button = page.getByRole("link", { name: "Continue with Google" });
    test.skip((await button.count()) === 0, "Google sign-in isn't configured on this API");
    await button.click();
    await expect(page.getByText("Google sign-in (test)")).toBeVisible();
    return target!;
  }

  test("the button sends you to Google with state, PKCE and this site's callback", async ({ page }) => {
    const target = await startGoogle(page);
    expect(target.searchParams.get("redirect_uri")).toMatch(/\/api\/auth\/oauth\/google\/callback$/);
    expect(target.searchParams.get("state")?.length).toBeGreaterThanOrEqual(40);
    expect(target.searchParams.get("code_challenge_method")).toBe("S256");
    expect(target.searchParams.get("scope")).toContain("email");
  });

  test("a return with the wrong state is refused", async ({ page }) => {
    await startGoogle(page);
    await go(page, "/api/auth/oauth/google/callback?code=abc&state=not-the-right-state-at-all");
    await expect(page).toHaveURL(/\/login\?error=oauth_expired/);
    await expect(page.getByRole("main").getByRole("alert")).toContainText("took too long");
  });

  test("a cancelled sign-in says so, and a failed one shows a clear message", async ({ page }) => {
    const target = await startGoogle(page);
    await go(page, "/api/auth/oauth/google/callback?error=access_denied");
    await expect(page.getByRole("main").getByRole("alert")).toContainText("cancelled");

    // the state is single use, so start again; this time the code can't be exchanged
    const again = await startGoogle(page);
    expect(again.searchParams.get("state")).not.toBe(target.searchParams.get("state"));
    await go(page, `/api/auth/oauth/google/callback?code=fake-code&state=${again.searchParams.get("state")}`);
    await expect(page.getByRole("main").getByRole("alert")).toContainText("didn't go through");
  });

  test("error codes show fixed messages, never text from the link", async ({ page }) => {
    await go(page, "/login?error=Call%20555-0100%20to%20verify");
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  });
});

test("a guest resume moves into the account, and never shows for anyone else", async ({ page }) => {
  // check a resume while signed out
  await go(page, "/resume");
  await page.getByLabel("Resume file").setInputFiles(RESUME);
  await expect(page.getByText(/Resume strength/)).toBeVisible({ timeout: 15000 });

  // sign up: the resume moves to the account
  await signUp(page, "owner");
  await go(page, "/resume");
  await expect(page.getByRole("heading", { name: "Your resumes" })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Used for matching")).toBeVisible();

  // sign out, without reloading the page: no resume is left behind
  await page.locator("summary", { hasText: "Account menu" }).click();
  await page.locator("details[open]").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await go(page, "/resume");
  await expect(page.getByText(/Resume strength/)).toHaveCount(0);

  // a different account on the same browser sees nothing of the first one's
  await signUp(page, "someone-else");
  await go(page, "/resume");
  await expect(page.getByText(/Resume strength/)).toHaveCount(0);
  await go(page, "/jobs");
  await expect(page.getByText(/\d+% match/)).toHaveCount(0);
});

test("the builder reads in a resume file, coaches bullets and tailors to a job", async ({ page }) => {
  await go(page, "/resume/builder?new=1");
  await page.getByLabel("Resume file to import").setInputFiles(RESUME);
  await expect(page.getByLabel("Full name")).toHaveValue("Jordan Lee");
  await expect(page.getByLabel("Company").first()).toHaveValue("Maple Ledger Bank");
  await expect(page.getByText("Start with what you did, not your duty").first()).toBeVisible();
  await expect(page.getByText("Fits on one page.")).toBeVisible();

  await page.getByPlaceholder("Search jobs, e.g. data engineering intern").fill("Data Engineering");
  await page.getByRole("button", { name: /Data Engineering Intern/ }).first().click();
  const panel = page.getByRole("region", { name: "Tailor to a job" });
  await expect(panel.getByText("Tailoring to")).toBeVisible();
  await expect(panel.getByRole("img", { name: /out of 100/ })).toBeVisible({ timeout: 10_000 });
});
