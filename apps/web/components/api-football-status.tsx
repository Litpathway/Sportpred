"use client";
import { useApi } from "@/hooks/use-api";
import { kickoff, readable } from "@/lib/api";
import { Badge, SectionTitle } from "@/components/common";

interface Connection {
  configured: boolean;
  key_present: boolean;
  daily_budget: number;
  pipeline_interval_minutes: number;
  account: {plan?: string; active?: boolean; observed_at?: string; requests?: {current?: number; limit_day?: number}} | null;
  last_warnings: {reason?: string; detail?: string; league_slug?: string}[];
  last_error?: {reason?: string; endpoint?: string} | null;
}
interface SportyBetStatus {
  enabled: boolean; region: string;
  sync?: {status: string; matched_fixtures: number; observed_at: string} | null;
}

export function ApiFootballStatus() {
  const query = useApi<{api_football?: Connection; sportybet_odds?: SportyBetStatus}>("/admin/providers");
  const connection = query.data?.api_football;
  if (!connection?.configured) return null;
  return <section className="panel provider-card">
    <SectionTitle title="API-Football connection" description="Server-side credentials, subscription status and import coverage."/>
    <Badge tone={connection.key_present ? "green" : "red"}>{connection.key_present ? "API key configured" : "API key missing"}</Badge>
    <dl><dt>Subscription</dt><dd>{connection.account?.plan || "Awaiting first successful sync"}</dd>
      <dt>Site request budget</dt><dd>{connection.daily_budget} requests/day</dd>
      <dt>Scheduled refresh</dt><dd>Every {connection.pipeline_interval_minutes} minutes</dd>
      {connection.account?.observed_at && <><dt>Account checked</dt><dd>{kickoff(connection.account.observed_at)} WAT</dd></>}
    </dl>
    <p>Fixtures and odds depend on your subscription’s season coverage. Calibrated predictions require sufficient verified history and a separately approved model.</p>
    {connection.last_error && <p className="field-error">Latest provider error: {readable(connection.last_error.reason || "unavailable")}. Check your API-Football account and season access.</p>}
    {!!connection.last_warnings.length && <div className="reason-box"><strong>Latest import notices</strong>
      {connection.last_warnings.slice(0,12).map((warning, index) => <span key={index}>
        {warning.league_slug ? `${readable(warning.league_slug)}: ` : ""}{readable(warning.reason || "Provider notice")}
        {warning.detail ? ` — ${warning.detail}` : ""}
      </span>)}
    </div>}
    {query.data?.sportybet_odds?.enabled && <div className="provider-card">
      <SectionTitle title="SportyBet odds overlay" description="Read-only market quotes matched to existing API-Football fixtures."/>
      <Badge tone={query.data.sportybet_odds.sync?.status === "ok" ? "green" : "amber"}>{readable(query.data.sportybet_odds.sync?.status || "waiting for sync")}</Badge>
      <dl><dt>Region</dt><dd>{query.data.sportybet_odds.region}</dd>
        <dt>Matched fixtures</dt><dd>{query.data.sportybet_odds.sync?.matched_fixtures ?? 0}</dd>
        {query.data.sportybet_odds.sync?.observed_at && <><dt>Last read</dt><dd>{kickoff(query.data.sportybet_odds.sync.observed_at)} WAT</dd></>}
      </dl>
      <p>Unofficial feed. Odds are snapshots, not model probabilities. No booking or wager is submitted.</p>
    </div>}
  </section>;
}
