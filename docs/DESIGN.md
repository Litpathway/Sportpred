# SportPredict AI — approved interface and verification

## Approved direction

The user's screenshot of https://sportpred.vercel.app is the visual source of truth. Preserve the light blue-gray workspace, white sidebar, mint/green accents, existing sans-serif type, rounded statistic panels, evidence-first hero and fixture spotlight cards. The alternate paper/forest editorial design was reverted locally after the user confirmed that they love the existing design. It was never deployed.

The original stylesheet, dashboard composition, charts and team mark colors are restored exactly from the clean starting checkout. Public navigation labels and workspace copy are retained. Existing Next.js/FastAPI workflows, provider integrations, approval rules and live data behavior are retained.

## Reference research

All ten requested resources were opened before implementation. Public page content was researched; unavailable gallery images were not treated as visually verified examples. Their principles are subordinate to the user's approved screenshot.

| Reference | Useful principle | Application within the approved design |
| --- | --- | --- |
| [Land-book](https://land-book.com/) | Compare whole-page hierarchy and mobile layouts. | Retain the established overview, hero, statistics and spotlight sequence. |
| [Supahero: David Alaba](https://supahero.io/hero/david-alaba) and [Linear](https://supahero.io/hero/linear) | Subject-specific, clear product positioning. | Preserve the existing football evidence headline and functional high-confidence CTA. |
| [Navbar Gallery](https://www.navbar.gallery/blog/sidebar-navigation) | Persistent navigation suits several research destinations. | Keep the white sidebar; improve its mobile keyboard semantics without changing appearance. |
| [Social Proof Examples](https://socialproofexamples.com/) | Evidence should be specific and inspectable. | Keep actual API counts, simulation labels and outcome records; add no testimonials or fabricated statistics. |
| [Deck Gallery](https://www.deck.gallery/) | Deliberate information pacing. | Keep the existing hierarchy and contextual methodology explanations. |
| [OG Image Gallery](https://www.ogimage.gallery/) | A social preview needs a concise branded hierarchy. | Add an original 1200 × 630 social image in the approved navy, white and green family. |

[Pricing Pages](https://pricingpages.design/), [Really Good Emails](https://reallygoodemails.com/), [Posts Design](https://posts.design/) and [Adfolio](https://www.adfolio.design/) were examined for applicability. No pricing, email lifecycle, advertising or launch-asset workflow was requested, so those patterns were not added.

## Existing design system retained

The effective light theme uses background `#f3f7fb`, white surfaces, text `#12243b`, muted text `#64748b`, borders `#e2e9f0` and green accent `#08b86b`. Existing system sans-serif typography, spacing, breakpoints, corner radii, iconography, card layouts, logo fallbacks and chart styling remain intact. No font, image or frontend dependency was added.

## Improvements retained

- A closed mobile sidebar is inert, so its offscreen links cannot receive keyboard focus. An open mobile drawer has a dialog label; resizing to desktop closes the mobile state.
- Prediction tables have column-header scopes, a hidden caption and a keyboard-focusable scroll region.
- Public routes have page-specific titles; login and administration routes request no indexing.
- Open Graph/Twitter metadata and an original social preview match the approved visual identity.
- Optional local build/browser memory limits support this constrained Windows host.

Set `NEXT_PUBLIC_SITE_URL` to the canonical HTTPS origin on custom hosting. Vercel's `VERCEL_PROJECT_PRODUCTION_URL` is used when available; local builds use `http://localhost:3000`. This follows the [Next.js metadata API](https://nextjs.org/docs/app/api-reference/functions/generate-metadata).

## Verification

TypeScript passes after restoring the approved interface. The earlier alternate design passed a bounded production webpack build and 28 mocked Chromium scenarios, but those are not presented as proof for the restored interface. Current browser verification is recorded below. No production deployment, live provider request, real administrator mutation, screen-reader audit, real-device test or Lighthouse run was performed.

On this Windows host, use `NEXT_BUILD_CPUS=1`, `NODE_OPTIONS=--max-old-space-size=1024 --v8-pool-size=1`, `RAYON_NUM_THREADS=1` and `UV_THREADPOOL_SIZE=1` with `next build --webpack`. Unbounded build/browser attempts exhausted host memory. For browser QA, `PLAYWRIGHT_LOW_MEMORY=1` selects reduced-memory Chromium arguments; `PLAYWRIGHT_EXECUTABLE_PATH` can select installed Chrome. These settings are optional and do not change production behavior.

## Current quality audit

Scores are bounded design assessments, not certification. The approved visual identity takes precedence over stylistic novelty.

| Criterion | Assessment | Basis / limit |
| --- | --- | --- |
| Brand distinctiveness | 8/10 | User-approved football analytics identity is preserved. |
| Visual hierarchy | 8/10 | Hero, statistics and fixture research follow the established hierarchy. |
| Typography quality | 8/10 | Existing readable sans-serif system is retained. |
| Layout originality | 7/10 | Familiar dashboard patterns suit the product and are explicitly preferred by the user. |
| Color coherence | 8/10 | Existing navy, white and mint/green palette is preserved. |
| Navigation usability | 8/10 | Existing destinations remain; mobile keyboard behavior is improved. |
| Content authenticity | 8/10 | API records and simulation labels remain; no invented credibility claims. |
| Mobile experience | 7/10 | Existing responsive layouts retained; real-device testing remains outstanding. |
| Accessibility | 7/10 | Improved drawer semantics and table navigation; full screen-reader/contrast audit remains outstanding. |
| Functional completeness | 7/10 | Existing workflows preserved; production feeds and real mutations were not reverified. |

The weakest areas needing engineering attention were accessibility, mobile task access and functional verification. Retained improvements address offscreen keyboard focus, keyboard table scrolling and regression coverage. No visual redesign is required to address those areas. Scores remain cautious because frontend contract tests do not establish live integration correctness.

Browser verification: **20/20 desktop/mobile Chromium scenarios passed** on the local interface, and desktop/mobile screenshots were visually inspected against the approved direction. A follow-up run after two wording-only edits passed the 10 desktop scenarios, then its first mobile scenario timed out at 55 seconds on this resource-constrained host. The edits changed the overview section heading to “Latest predictions” and the breadcrumb fallback to “Match details”; no interaction or layout code changed. TypeScript and `git diff --check` pass. Test data is fictional; live production feeds were not used. The current revision was not rebuilt for production or deployed.
