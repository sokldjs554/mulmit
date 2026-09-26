import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack: the API on :8000 with the seeded demo world
 * (`make demo`) and the production web build on :3000. CI starts both in the "E2E" job.
 *
 * No retries: a test that passes on the second try is hiding a bug, not a flake.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // a preinstalled Chromium when the pinned browser build is not downloaded (e.g. a sandbox)
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
