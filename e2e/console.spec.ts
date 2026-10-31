import { expect, type Page, test } from "@playwright/test";

const token = (name: string) => `test-${name}-${"x".repeat(40)}`;
async function login(page: Page, name = "operator") {
  await page.getByLabel("Bearer credential").fill(token(name));
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("button", { name: "Switch identity" })).toBeVisible();
}
test("console displays persisted diagnostics and responsive evidence", async ({ page, request }) => {
  for (const [i, book] of [
    "performance",
    "filesystem",
    "network",
    "tls",
    "kubernetes",
    "pipeline",
    "logs",
    "cloud",
    "security",
    "service",
  ].entries()) {
    const response = await request.post("/api/runs", {
      headers: { Authorization: `Bearer ${token("operator")}`, "Idempotency-Key": `browser-seed-${i}` },
      data: { runbook: book, target: "fixture", scenario: i % 3 === 0 ? "healthy" : "failure" },
    });
    expect(response.status()).toBe(201);
  }
  await page.goto("/");
  await login(page);
  await expect(page.getByRole("heading", { name: "Keep operations moving." })).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/overview.png", fullPage: true });
  await page.getByRole("button", { name: "Automations", exact: true }).click();
  await expect(page.locator("article.book")).toHaveCount(10);
  await page.screenshot({ path: "docs/screenshots/catalog.png", fullPage: true });
  await page
    .locator("article.book")
    .filter({ has: page.getByRole("heading", { name: "Performance", exact: true }) })
    .getByRole("button", { name: "Run →" })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("Sustained load exceeds CPU capacity")).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/evidence.png", fullPage: true });
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: "docs/screenshots/mobile.png", fullPage: true });
});
test("operator and independent approver complete verified recovery", async ({ page }) => {
  await page.goto("/");
  await login(page);
  await page.getByRole("button", { name: "Inject lab failure" }).click();
  await expect(page.getByRole("status")).toContainText("failure injected");
  await page.getByRole("button", { name: "Automations", exact: true }).click();
  await page.getByLabel("Target", { exact: true }).selectOption("lab");
  await page
    .locator("article.book")
    .filter({ has: page.getByRole("heading", { name: "Service", exact: true }) })
    .getByRole("button", { name: "Run →" })
    .click();
  await page.getByRole("button", { name: "Request recovery approval" }).click();
  await expect(page.getByText("Recovery requested.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Switch identity" }).click();
  await login(page, "approver");
  await page.getByLabel("Decision reason").fill("Approved isolated service recovery");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("button", { name: "Execute recovery" })).toBeVisible();
  await page.getByRole("button", { name: "Switch identity" }).click();
  await login(page);
  await page.getByRole("button", { name: "Execute recovery" }).click();
  await expect(page.getByRole("dialog")).toContainText("Recovery succeeded. Verification: true.");
});
test("failed authentication remains visible and safe", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Bearer credential").fill(`invalid-${"x".repeat(40)}`);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("valid bearer credential required");
});
