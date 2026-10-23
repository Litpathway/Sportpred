import {test,expect} from "@playwright/test";
import {readFileSync,existsSync} from "node:fs";
import path from "node:path";

test.skip(!process.env.E2E_LIVE,"Requires a seeded running FastAPI backend; see README.");

test("real database predictions flow through match analysis",async({page},testInfo)=>{
  await page.goto("/");await expect(page.getByRole("heading",{name:"A clearer view of the game."})).toBeVisible();
  await expect(page.locator(".predictions-table tbody tr").first()).toBeVisible();
  const dimensions=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:document.documentElement.clientWidth}));
  expect(dimensions.width, "The real dashboard must fit the viewport").toBe(dimensions.viewport);
  await page.screenshot({path:testInfo.outputPath("dashboard.png"),fullPage:true,scale:"css"});
  await page.locator(".match-cell").first().click();await expect(page.getByRole("heading",{name:"Behind the prediction"})).toBeVisible();
  await expect(page.locator(".market-row")).toHaveCount(10);
  await expect(page.locator(".model-reference")).toContainText("ensemble-v1-demo");
});

test("real admin authentication and reversible settings update",async({page})=>{
  const envPath=path.resolve("../../.env");const local=existsSync(envPath)?Object.fromEntries(readFileSync(envPath,"utf8").split(/\r?\n/).filter(l=>l&&!l.startsWith("#")).map(l=>{const i=l.indexOf("=");return [l.slice(0,i),l.slice(i+1)];})):{};
  const email=process.env.E2E_ADMIN_EMAIL||local.ADMIN_EMAIL;const password=process.env.E2E_ADMIN_PASSWORD||local.ADMIN_PASSWORD;
  test.skip(!email||!password,"Admin credentials not configured");
  await page.goto("/login");await page.getByLabel("Email address").fill(email);await page.getByLabel("Password",{exact:true}).fill(password);await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await expect(page).toHaveURL(/\/admin$/);await page.getByRole("link",{name:"Settings",exact:true}).click();
  const threshold=page.getByLabel("Minimum probability",{exact:false});const original=await threshold.inputValue();
  await threshold.fill("0.81");await page.getByRole("button",{name:"Save settings"}).click();await expect(page.getByRole("status")).toContainText("Changes saved");
  await threshold.fill(original);await page.getByRole("button",{name:"Save settings"}).click();await expect(page.getByRole("status")).toContainText("Changes saved");
  await page.getByRole("button",{name:"Sign out"}).click();await expect(page).toHaveURL(/\/login$/);
});
