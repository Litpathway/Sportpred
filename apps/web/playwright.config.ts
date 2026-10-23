import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", fullyParallel: false, workers: 1, timeout: 45000,
  expect: {timeout: 10000}, reporter: "list",
  use: {baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure", screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH} : undefined},
  projects: [{name:"desktop",use:{...devices["Desktop Chrome"],viewport:{width:1440,height:1100}}},
    {name:"mobile",use:{...devices["iPhone 13"],defaultBrowserType:"chromium",deviceScaleFactor:1}}],
  webServer: {command:"npm run start -- --port 3100",url:"http://127.0.0.1:3100",reuseExistingServer:!process.env.CI,timeout:120000},
});
