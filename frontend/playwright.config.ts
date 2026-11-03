import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 8765);

/**
 * Browser end-to-end tests against the production build served by FastAPI, with a fixture
 * card database. Run `npm run build` first. Nothing here touches the Internet.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  // CI's hosted runners differ about 2x in speed from run to run (the same browser suite took 11 to 23 minutes, the
  // same backend job 8 to 16): the multi-browser LAN tests get room for a slow runner there. Locally the budget stays
  // tight, so a real slowdown still shows.
  timeout: process.env.CI ? 120_000 : 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]] : "list",
  outputDir: "test-results/artifacts",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    launchOptions: {
      // Talk to the table directly (a system HTTP proxy would intercept LAN WebSocket upgrades).
      // WebGL for the 3D table in headless Chromium (software rendering)
      args: ["--no-proxy-server", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
      ...(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {}),
    },
  },
  webServer: {
    command: "bash ../scripts/e2e-server.sh",
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
    env: { E2E_PORT: String(PORT) },
  },
});
