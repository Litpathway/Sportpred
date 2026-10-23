import { test, expect } from "@playwright/test";

const fixture={id:1,home:"Northbridge FC",away:"Briarwood",competition:"England Demo League",country:"England",kickoff:"2026-11-01T15:00:00Z",status:"scheduled",simulated:true,home_goals:null,away_goals:null,synced_at:"2026-10-23T12:00:00Z",odds_at:"2026-10-23T12:00:00Z",enrichment:{}};
const prediction={id:1,fixture,market:"home_or_draw",market_label:"Home or draw",probability:.84,raw_probability:.86,quality:.85,odds:1.14,eligible:true,reasons:[],outcome:"pending",explanation:"A calibrated estimate based on prior results.",features:{values:{home_scored:2.1,away_scored:1.1},missing:["xg","injuries"],home_form:["W","W","L","D","W"],away_form:["L","L","W","D","L"],as_of:"2026-10-23T12:00:00"},created_at:"2026-10-23T12:00:00Z",model:"demo-test",model_approved:true};
const performance={total:1,won:0,lost:0,void:0,pending:1,accuracy:null,metrics:null,roi:null,roi_assumptions:"Hypothetical flat one-unit stakes, no money staked.",by_market:[],by_probability_band:[],by_model:[],history:[],simulated:true};
const overview={upcoming_matches:12,eligible_predictions:1,verified_codes:0,competitions:3,threshold:.8,demo_mode:true,publication_paused:false,model:null,performance};
const leagues=["Premier League","La Liga","Bundesliga","Serie A","Ligue 1","Eredivisie","Primeira Liga","Belgian Pro League","Süper Lig","Scottish Premiership"].map((name,i)=>({slug:String(i),name,country:"Europe",fixtures:0,status:"awaiting_feed"}));

test.beforeEach(async({page})=>{
  await page.route("**/api/**",async route=>{
    const url=new URL(route.request().url());let data:unknown={};let status=200;
    if(url.pathname==="/api/overview")data=overview;
    else if(url.pathname==="/api/competitions")data=[{id:1,name:fixture.competition}];
    else if(url.pathname==="/api/league-coverage")data=leagues;
    else if(url.pathname==="/api/fixtures/1")data={fixture,predictions:[prediction],data_status:"available"};
    else if(url.pathname==="/api/fixtures")data={items:url.searchParams.get("q")==="Missing"?[]:[fixture],total:url.searchParams.get("q")==="Missing"?0:1};
    else if(url.pathname==="/api/predictions")data={items:[prediction],total:1};
    else if(url.pathname==="/api/slips")data={items:[],total:0};
    else if(url.pathname==="/api/performance")data=performance;
    else if(url.pathname.startsWith("/api/auth/")||url.pathname.startsWith("/api/admin/")){status=401;data={detail:"Admin sign-in required"};}
    await route.fulfill({status,contentType:"application/json",body:JSON.stringify(data)});
  });
});

test("overview labels simulations and uses API counts",async({page})=>{
  await page.goto("/");await expect(page.getByRole("heading",{name:"A clearer view of the game."})).toBeVisible();
  await expect(page.getByText("Demo workspace",{exact:true})).toBeVisible();
  await expect(page.locator(".stat-value").first()).toHaveText("12");
  await expect(page.getByText("84.0%",{exact:true})).toBeVisible();
  await expect(page.getByText("Settled accuracy",{exact:true})).toBeVisible();
  await expect(page.locator("html")).toHaveJSProperty("scrollWidth",await page.evaluate(()=>document.documentElement.clientWidth));
});

test("search, empty state and match analysis",async({page})=>{
  await page.goto("/matches");await expect(page.getByRole("link",{name:/England Demo League.*Simulated/})).toBeVisible();
  await page.getByRole("textbox",{name:"Search matches"}).fill("Missing");await expect(page.getByRole("heading",{name:"No matches found"})).toBeVisible();
  await page.getByRole("textbox",{name:"Search matches"}).fill("Northbridge");
  await page.locator(".match-card").first().click();await expect(page.getByRole("heading",{name:"The match, beyond the odds."})).toBeVisible();
  await expect(page.getByText("84.0%",{exact:true}).first()).toBeVisible();
  await expect(page.getByRole("heading",{name:"What the data doesn’t tell us"})).toBeVisible();
});

test("ten-league coverage shows missing live data without fabricating fixtures",async({page})=>{
  await page.goto("/matches");
  await page.getByText("European league coverage",{exact:true}).click();
  await expect(page.locator(".league-coverage-grid>div")).toHaveCount(10);
  await expect(page.getByText("Awaiting feed",{exact:true})).toHaveCount(10);
  await expect(page.getByText("Scottish Premiership",{exact:true})).toBeVisible();
  await expect(page.locator("html")).toHaveJSProperty("scrollWidth",await page.evaluate(()=>document.documentElement.clientWidth));
});

test("imported form is shown without inventing model probabilities",async({page})=>{
  await page.route("**/api/fixtures/1",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({fixture,predictions:[],evidence:prediction.features,data_status:"insufficient_data"})}));
  await page.goto("/matches/1");
  await expect(page.getByRole("heading",{name:"Current team form"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Insufficient prediction data"})).toBeVisible();
  await expect(page.locator(".market-row")).toHaveCount(0);
  await expect(page.getByText("84.0%",{exact:true})).toHaveCount(0);
});

test("verified-code feed refuses to fabricate a code",async({page})=>{
  await page.goto("/booking-codes");await expect(page.getByRole("heading",{name:"No verified codes published"})).toBeVisible();
  await page.getByRole("button",{name:"All publications"}).click();await expect(page.getByRole("heading",{name:"No publications yet"})).toBeVisible();
});

test("performance separates unpublished history from evaluation",async({page})=>{
  await page.goto("/performance");await expect(page.getByRole("heading",{name:"The track record starts with settlement"})).toBeVisible();
  await expect(page.getByText("No published predictions have settled yet.",{exact:false})).toBeVisible();
});

test("admin routes redirect to login and show errors",async({page})=>{
  await page.goto("/admin/settings");await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email address").fill("wrong@example.test");await page.getByLabel("Password",{exact:true}).fill("wrong-password");await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Admin sign-in required");
});

test("API failures show a recoverable error state",async({page})=>{
  await page.route("**/api/fixtures?**",route=>route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"Fixture service unavailable"})}));
  await page.goto("/matches");await expect(page.getByRole("main").getByRole("alert")).toContainText("Fixture service unavailable");await expect(page.getByRole("button",{name:"Try again"})).toBeVisible();
});

test("mobile navigation exposes active routes and closes with Escape",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/predictions/high-confidence");
  const menu=page.getByRole("button",{name:"Open navigation"});
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded","true");
  await expect(page.getByRole("link",{name:/High confidence/})).toHaveAttribute("aria-current","page");
  await page.keyboard.press("Escape");
  await expect(menu).toHaveAttribute("aria-expanded","false");
  await menu.click();
  await page.getByRole("link",{name:"Performance"}).click();
  await expect(page).toHaveURL(/\/performance$/);
  await expect(menu).toHaveAttribute("aria-expanded","false");
});

test("admin workspace explains navigation, actions and model training",async({page})=>{
  await page.route("**/api/auth/me",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({email:"admin@example.test",role:"admin",csrf_token:"test-csrf"})}));
  await page.route("**/api/admin/overview",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({...overview,failed_jobs:0})}));
  await page.route("**/api/admin/jobs",route=>route.fulfill({status:200,contentType:"application/json",body:"[]"}));
  await page.route("**/api/admin/audit",route=>route.fulfill({status:200,contentType:"application/json",body:"[]"}));
  await page.route("**/api/admin/models",route=>route.fulfill({status:200,contentType:"application/json",body:"[]"}));
  await page.goto("/admin");
  await expect(page.getByRole("heading",{name:"Admin overview"})).toBeVisible();
  await expect(page.getByRole("navigation",{name:"Admin sections"}).getByRole("link",{name:"Models & data"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Run publication pipeline"})).toBeVisible();
  await expect(page.getByText(/does not train or approve a model/i)).toBeVisible();
  await page.getByRole("navigation",{name:"Admin sections"}).getByRole("link",{name:"Models & data",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Models and training data"})).toBeVisible();
  await expect(page.getByText("Choose a results CSV")).toBeVisible();
  await expect(page.getByText(/Training creates a version for review/i).first()).toBeVisible();
});
