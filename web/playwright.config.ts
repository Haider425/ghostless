import { defineConfig, devices } from "@playwright/test";

/*
  End-to-end tests run against a production build and a live API with demo
  data (see the "web" job in .github/workflows/ci.yml). Locally:

    python scripts/seed_demo.py --yes && ghostless serve     # terminal 1
    npm run build && npm run test:e2e                        # terminal 2

  Set PLAYWRIGHT_CHROMIUM to use an already-installed Chromium.
*/

const port = Number(process.env.PORT ?? 3100);
const executablePath = process.env.PLAYWRIGHT_CHROMIUM;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  // the longest tests sign up two accounts and visit several pages; CI machines are slower
  timeout: process.env.CI ? 60_000 : 30_000,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    launchOptions: executablePath ? { executablePath } : undefined,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: {
    command: `npx next start -p ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
