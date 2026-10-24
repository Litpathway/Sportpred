"use client";
import Link from "next/link";
import { ArrowUpRight, Check, Clock3 } from "lucide-react";
import { Prediction } from "@/types/api";
import { kickoff, percent, readable } from "@/lib/api";
import { Badge, TeamMark } from "@/components/common";

const reviewLabels: Record<string, string> = {
  below_probability_threshold: "Below confidence threshold",
  poor_data_quality: "Data quality check failed",
  model_not_approved: "Model not approved",
  model_data_domain_mismatch: "Model data mismatch",
  model_temporal_leakage: "Model timing check failed",
  unsupported_market: "Market unavailable",
  fixture_not_upcoming: "Fixture is no longer upcoming",
  stale_fixture_data: "Fixture data needs refresh",
  stale_or_missing_odds: "Odds need refresh",
  stale_prediction: "Estimate needs refresh",
};

export function PredictionTable({items, selected, onSelect}: {items: Prediction[]; selected?: number[]; onSelect?: (id: number) => void}) {
  return <div className="table-scroll" role="region" aria-label="Prediction records, scroll for more columns" tabIndex={0}><table className="data-table predictions-table"><caption className="sr-only">Model predictions, probability estimates and recorded outcomes</caption><thead><tr>{onSelect && <th scope="col">Select</th>}<th scope="col">Match / competition</th><th scope="col">Prediction</th><th scope="col">Probability</th><th scope="col">Odds</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Analysis</span></th></tr></thead><tbody>{items.map(p => <tr key={p.id}>
    {onSelect && <td><input type="checkbox" aria-label={`Select prediction ${p.id}`} checked={selected?.includes(p.id) ?? false} onChange={() => onSelect(p.id)} disabled={!p.eligible}/></td>}
    <td><Link className="match-cell" href={`/matches/${p.fixture.id}`}><span className="mini-teams"><TeamMark name={p.fixture.home} logo={p.fixture.home_logo}/><TeamMark name={p.fixture.away} logo={p.fixture.away_logo}/></span><span><strong>{p.fixture.home} <span className="muted vs">vs</span> {p.fixture.away}</strong><small>{p.fixture.competition} <span>·</span> {kickoff(p.fixture.kickoff)}</small></span></Link></td>
    <td><span className="market-cell">{p.market_label}</span></td><td><div className="probability-cell"><strong className={p.eligible ? "text-green" : ""}>{percent(p.probability, 1)}</strong><div className="probability-track"><span style={{width: percent(p.probability)}}/></div></div></td>
    <td className="odds-cell">{p.odds?.toFixed(2) ?? "—"}</td><td>{p.outcome !== "pending" ? <Badge tone={p.outcome === "won" ? "green" : p.outcome === "lost" ? "red" : "neutral"}>{readable(p.outcome)}</Badge> : p.eligible ? <Badge tone="green"><Check size={11}/> Eligible</Badge> : <div className="prediction-status"><Badge tone="amber"><Clock3 size={11}/> Needs review</Badge><small className="prediction-reason">{p.reasons.length ? p.reasons.map(reason => reviewLabels[reason] ?? readable(reason)).join(" · ") : "Eligibility checks not met"}</small></div>}</td>
    <td><Link href={`/matches/${p.fixture.id}`} className="table-arrow" aria-label={`Analyze ${p.fixture.home} versus ${p.fixture.away}`}><ArrowUpRight size={17}/></Link></td>
  </tr>)}</tbody></table></div>;
}
