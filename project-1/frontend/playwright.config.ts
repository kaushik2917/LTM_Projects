import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:3000", channel: "msedge", headless: true, screenshot: "only-on-failure", trace: "retain-on-failure" },
});
