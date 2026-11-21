// Real Electron + FastAPI smoke test. Only the native folder dialog is substituted.
const { _electron: electron, expect } = require("@playwright/test");
const { resolve } = require("node:path");
const { mkdtemp, rm } = require("node:fs/promises");
const { tmpdir } = require("node:os");

(async () => {
  const profile = await mkdtemp(resolve(tmpdir(), "nodeglass-desktop-"));
  let app, page, backendUrl;
  const failures = [];
  try {
    app = await electron.launch({
      executablePath: process.env.NODEGLASS_ELECTRON_EXECUTABLE,
      args: [".", "--user-data-dir=" + profile],
      cwd: resolve(__dirname, ".."),
      timeout: 40000,
    });
    page = await app.firstWindow();
    backendUrl = await page.evaluate(
      async () => (await window.nodeglass.connection()).url,
    );
    page.on("console", (msg) => {
      if (["error", "warning"].includes(msg.type()))
        console.log("Renderer:", msg.text());
    });
    page.on("pageerror", (error) => failures.push(error.message));
    await expect(
      page.getByRole("heading", { name: "Understand the connections." }),
    ).toBeVisible();
    await app.evaluate(
      ({ dialog }, folder) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [folder],
        });
      },
      resolve(__dirname, "../../fixtures/example"),
    );
    await page
      .getByRole("button", { name: "Open repository", exact: true })
      .click();
    await expect(
      page.getByText("Analysis complete", { exact: true }),
    ).toBeVisible({ timeout: 20000 });
    await expect(page.locator(".react-flow__node")).toHaveCount(3);
    await expect(page.locator(".react-flow__edge")).toHaveCount(2);
    await page.getByRole("button", { name: "Call graph", exact: true }).click();
    await page
      .locator(".react-flow__node")
      .filter({ has: page.locator("strong", { hasText: /^login$/ }) })
      .click();
    await expect(page.locator(".inspection h2")).toHaveText("login");
    await expect(page.locator(".inspection")).toContainText(
      "username, password",
    );
    await page.getByRole("button", { name: "Downstream", exact: true }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(3);
    await expect(page.locator(".react-flow__edge")).toHaveCount(2);
    await expect(
      page.locator(".react-flow__edge").filter({ hasText: "conditional" }),
    ).toHaveCount(1);
    await page
      .getByRole("button", { name: "View function flow", exact: true })
      .click();
    await expect(
      page.locator(".react-flow__node").filter({ hasText: "if_statement" }),
    ).toHaveCount(1);
    await expect(page.locator(".react-flow__node")).not.toHaveCount(0);
    await page.screenshot({
      path: resolve(__dirname, "../test-results/function-flow.png"),
    });
    await page.getByRole("button", { name: "Scan", exact: true }).click();
    await expect(
      page.getByText("Analysis complete", { exact: true }),
    ).toBeVisible({ timeout: 20000 });
    expect(failures).toEqual([]);
    console.log(
      "PASS: Electron folder workflow, real backend scan, dependency/call/flow rendering, conditional edges, inspector, rescan.",
    );
  } catch (error) {
    if (page) {
      console.log(await page.locator("body").innerText());
      await page.screenshot({
        path: resolve(__dirname, "../test-results/failure.png"),
      });
    }
    throw error;
  } finally {
    if (app) await app.close();
    if (backendUrl)
      await expect
        .poll(
          async () => {
            try {
              await fetch(backendUrl + "/health", {
                signal: AbortSignal.timeout(1000),
              });
              return false;
            } catch {
              return true;
            }
          },
          { timeout: 5000 },
        )
        .toBe(true);
    await rm(profile, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
