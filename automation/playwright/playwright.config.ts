import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    // The Target SUT base URL — adjust via env if your stack uses non-default
    // host ports (see planning/PLAN.md Phase 1 host port mapping table).
    baseURL: process.env.TARGET_SUT_URL ?? "http://localhost:18000",
  },
});
