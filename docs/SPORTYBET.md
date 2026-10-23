# SportyBet odds overlay

This optional adapter imports current market quotes from the Nigerian SportyBet feed and attaches them to exact API-Football fixture matches. It does not create fixtures, historical results, model probabilities, booking codes, or wagers. A fixture must match league, normalized home and away names, and kickoff within 15 minutes before any odds are attached.

The reference project is [Sportybet-mcp](https://github.com/UbongErnest/Sportybet-mcp). It describes SportyBet's public website feed as an undocumented, unofficial API that can change. This integration uses that read-only contract as a server-side overlay; it does not run an MCP stdio server inside Vercel. The repository's booking-code creation and status tools are not enabled in this site.

## Configuration

Set these server-side Vercel variables to enable the overlay:

| Variable | Default | Description |
| --- | --- | --- |
| `SPORTYBET_ODDS_ENABLED` | `false` | Enable the read-only feed during fixture syncs |
| `SPORTYBET_REGION` | `ng` | SportyBet region code; the adapter sends the matching country header |
| `SPORTYBET_CACHE_SECONDS` | `300` | Redis cache lifetime for the paginated feed |

The adapter requests football markets only, limits itself to five 100-event pages, waits at least 250 ms between requests, and caches responses in Redis. If the feed is unavailable, API-Football fixture and odds data remain in place. No raw upstream payloads or credentials are returned to the browser.

Quotes are shown on match detail pages with their source and observation time. They are not model probabilities. Model training still requires verified historical results; SportyBet's upcoming feed does not supply that history.
