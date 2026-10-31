import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8091",
    headless: true,
    viewport: { width: 1440, height: 1100 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: ".venv/bin/python -m scripts.e2e_server",
    url: "http://127.0.0.1:8091/api/health",
    reuseExistingServer: false,
    timeout: 20000,
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
