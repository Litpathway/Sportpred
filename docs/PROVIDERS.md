# Authorized integration contracts

These are **application-owned normalized gateway contracts**, not claims that a bookmaker or sports provider exposes these paths. Implement a gateway against the provider you are licensed and authorized to use, then configure the environment variables locally.

## Fixtures

`FIXTURE_PROVIDER=authorized` sends a bearer-authenticated HTTPS GET to the exact `FIXTURE_API_URL`. The body is `{"fixtures": [...]}`. The Pydantic `FixtureDTO` is the authoritative schema. Each fixture supplies:

```json
{
  "external_id": "provider-fixture-id",
  "competition": "Licensed Competition",
  "league_slug": "premier-league",
  "country": "England",
  "home": "Home Club",
  "away": "Away Club",
  "id_namespace": "licensed-feed",
  "home_external_id": "home-id",
  "away_external_id": "away-id",
  "competition_external_id": "competition-id",
  "kickoff": "2027-01-01T15:00:00+00:00",
  "status": "scheduled",
  "simulated": false,
  "odds": {"home_win": 1.8, "home_or_draw": 1.2},
  "odds_at": "2027-01-01T14:30:00+00:00",
  "enrichment": {
    "source": "licensed-feed",
    "as_of": "2027-01-01T14:30:00+00:00",
    "injuries": {"home": [], "away": ["Player identifier or display name"]}
  }
}
```

Statuses: scheduled/live/finished/cancelled/postponed. Finished records require integer `home_goals`, `away_goals` and timezone-aware `result_known_at`. The latter must reflect actual data availability, not the download time of a retrospective dataset unless first observation is all that is known. Do not send future lineups or post-match statistics as if they were pre-match inputs.

Supported markets: `home_win`, `draw`, `away_win`, `home_or_draw`, `away_or_draw`, `home_or_away`, `over_2_5`, `under_2_5`, `btts_yes`, `btts_no`. Odds must be decimal, >1, and timestamped. Missing odds remain missing. Optional enrichment supports timestamped per-side xG, shots, defense, injuries, suspensions and confirmed lineups. Unknown optional coverage is never replaced by a claim that no injuries exist.

Provider IDs are preferred when supplied; namespace both team IDs together. Otherwise the adapter uses explicit country-scoped name normalization. Alias reconciliation across licensed providers should be supplied by the gateway rather than guessed with fuzzy matching.

Authorized feeds must supply a canonical `league_slug` from the [ten-league catalog](VERCEL.md#ten-configured-domestic-leagues), with the matching country and `simulated=false`. Native `competition_external_id` stays separate. Missing/unknown league mappings fail validation before persistence; configured but disabled leagues are skipped with an audit warning. Cover all ten leagues in the provider subscription and gateway; setting the league list does not create provider coverage.

## Booking codes

`BOOKING_PROVIDER=authorized` requires `BOOKING_API_URL` (HTTPS base URL) and `BOOKING_API_TOKEN`. The app's normalized gateway uses these bearer-authenticated operations:

1. `POST /codes`, `Idempotency-Key` header, JSON `{"selections":[{"prediction_id":1,"fixture_id":2,"provider_fixture_id":"native-id","market":"home_win","decimal_odds":1.8}]}` → `{"code":"provider-returned-code"}`.
2. `POST /validate`, JSON `{"code":"..."}` → `{"valid":true,"genuine":true,"selection_ids":[1]}`.
3. `POST /status`, JSON `{"code":"..."}` → `{"status":"active"}` (or expired/cancelled/unknown).

The gateway must preserve the selection mapping and enforce the same idempotency key even after worker crashes. Validation must establish that the real code represents the **exact** selected fixtures and markets. A generic “code exists” response is insufficient. Mock-prefix codes, mismatched selections, unverified responses and any provider exception fall back to prediction-only publication. Simulated selections are never sent to a genuine provider.

There is no SportyBet endpoint implementation, token, scraper, account automation, stake, deposit, withdrawal or wager submission. Keep real code generation unavailable until your authorized provider supports this contract.
