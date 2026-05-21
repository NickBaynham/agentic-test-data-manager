// automation/playwright/take_audit_screenshot.mjs
//
// Capture a screenshot of the /ui/audit/{run_id} page for inclusion in the
// README and design docs. Requires a live ATDM stack (make up).
//
// Run via:  make audit-screenshot
//
// Lives in automation/playwright/ so Node ESM module resolution finds
// @playwright/test in the local node_modules. The target path is resolved
// relative to the repository root, not this script's directory.

import { chromium } from "@playwright/test";
import { resolve } from "node:path";

const REPO_ROOT = resolve(import.meta.dirname, "..", "..");

const ATDM = process.env.ATDM_API_URL ?? "http://localhost:18001";
const TOKEN = process.env.ATDM_API_TOKEN ?? "dev-token-change-me";
const SCENARIO = "claim_denial_active_member";
const TARGET =
  process.env.SCREENSHOT_OUT ?? resolve(REPO_ROOT, "docs/assets/audit-trail.png");

async function postJson(path, body) {
  const resp = await fetch(`${ATDM}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${TOKEN}`,
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`${path} returned ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

async function main() {
  console.log(`[screenshot] seeding ${SCENARIO} ...`);
  const seed = await postJson("/test-data/requests", {
    domain: "healthcare",
    scenario: SCENARIO,
    constraints: {},
    delivery: {
      seed_target: true,
      return_playwright_fixture: true,
      return_pytest_fixture: true,
    },
  });
  const runId = seed.test_run_id;
  console.log(`[screenshot] run_id=${runId}`);

  console.log("[screenshot] launching chromium ...");
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({
      viewport: { width: 1100, height: 900 },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const url = `${ATDM}/ui/audit/${runId}`;
    console.log(`[screenshot] navigating to ${url}`);
    await page.goto(url, { waitUntil: "networkidle" });
    // Auto-open the first event's details so the reviewer sees the expansion
    // is interactive, without bloating the PNG with every event's JSON.
    await page.evaluate(() => {
      const first = document.querySelector("details");
      if (first) first.setAttribute("open", "open");
    });
    console.log(`[screenshot] saving to ${TARGET}`);
    await page.screenshot({ path: TARGET, fullPage: true });
  } finally {
    await browser.close();
  }

  console.log("[screenshot] resetting run ...");
  await postJson(`/test-data/runs/${runId}/reset`, {
    cleanup_token: seed.cleanup.cleanup_token,
  });

  console.log("[screenshot] done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
