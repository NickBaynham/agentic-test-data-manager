/**
 * Example Playwright test consuming an ATDM-generated JSON fixture.
 *
 * Prerequisites:
 *   1. The local stack is up:           make up
 *   2. A scenario has been requested with --playwright:
 *        atdm request active_member_clean --playwright
 *      This writes <scenario>_<run_id>.json under automation/fixtures/.
 *   3. Set FIXTURE_PATH to point at the file before running:
 *        FIXTURE_PATH=../fixtures/active_member_clean_01XX.json \
 *          npx playwright test
 *
 * The test reads the fixture, hits the Target SUT's audit endpoint, and
 * asserts on the structure. End-to-end demo of the fixture contract.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { test, expect } from "@playwright/test";

type AtdmFixture = {
  scenario_id: string;
  test_run_id: string;
  data: {
    plan_id: string;
    provider_id: string;
    member_id: string;
    eligibility_id: string;
    claim_id: string;
  };
  cleanup: { cleanup_token: string; endpoint: string };
};

function loadFixture(): AtdmFixture {
  const fixturePath = process.env.FIXTURE_PATH;
  if (!fixturePath) {
    throw new Error(
      "FIXTURE_PATH env var must point at a JSON fixture emitted by `atdm request ... --playwright`"
    );
  }
  const resolved = path.resolve(fixturePath);
  const text = fs.readFileSync(resolved, "utf-8");
  return JSON.parse(text) as AtdmFixture;
}

test("ATDM fixture has the expected shape", () => {
  const fixture = loadFixture();
  expect(fixture.scenario_id).toBeTruthy();
  expect(fixture.test_run_id).toBeTruthy();
  expect(fixture.data.member_id).toMatch(/^m-/);
  expect(fixture.data.plan_id).toMatch(/^plan-/);
  expect(fixture.cleanup.cleanup_token).toBeTruthy();
  expect(fixture.cleanup.endpoint).toContain(fixture.test_run_id);
});

test("Target SUT health probe responds", async ({ request }) => {
  const response = await request.get("/health");
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.status).toBe("ok");
});
