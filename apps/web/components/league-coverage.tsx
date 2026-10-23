"use client";

import { useApi } from "@/hooks/use-api";
import { Badge, ErrorState, Loading } from "@/components/common";

interface LeagueCoverage {
  slug: string;
  name: string;
  country: string;
  fixtures: number;
  status: "data_received" | "awaiting_feed";
}

export function LeagueCoveragePanel() {
  const result = useApi<LeagueCoverage[]>("/league-coverage");
  return <details className="panel league-coverage">
    <summary>European league coverage</summary>
    <p>Configured leagues and real fixtures received. Feed coverage and data freshness determine which matches can be predicted.</p>
    {result.isPending ? <Loading/> : result.error ? <ErrorState error={result.error} retry={() => result.refetch()}/> :
      <div className="league-coverage-grid">{result.data?.map(league => <div key={league.slug}>
        <div><strong>{league.name}</strong><p>{league.country}</p></div>
        <Badge tone={league.status === "data_received" ? "green" : "neutral"}>
          {league.status === "data_received" ? `${league.fixtures} fixtures received` : "Awaiting feed"}
        </Badge>
      </div>)}</div>}
  </details>;
}
