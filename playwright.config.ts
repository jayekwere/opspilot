import { defineConfig } from "@playwright/test";

const port = process.env.OPSPILOT_TEST_PORT ?? "18091";
if (!/^\d{4,5}$/.test(port) || Number(port) > 65535) throw new Error("Invalid test port");
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 1100 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: ".venv/bin/python -m scripts.e2e_server",
    url: `${baseURL}/api/health`,
    env: { OPSPILOT_TEST_PORT: port },
    reuseExistingServer: false,
    timeout: 20000,
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
