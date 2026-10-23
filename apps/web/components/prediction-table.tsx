"use client";
import Link from "next/link";
import { ArrowUpRight, Check, Clock3 } from "lucide-react";
import { Prediction } from "@/types/api";
import { kickoff, percent, readable } from "@/lib/api";
import { Badge, TeamMark } from "@/components/common";

export function PredictionTable({items, selected, onSelect}: {items: Prediction[]; selected?: number[]; onSelect?: (id: number) => void}) {
  return <div className="table-scroll"><table className="data-table predictions-table"><thead><tr>{onSelect && <th>Select</th>}<th>Match / competition</th><th>Prediction</th><th>Probability</th><th>Odds</th><th>Status</th><th><span className="sr-only">Analysis</span></th></tr></thead><tbody>{items.map(p => <tr key={p.id}>
    {onSelect && <td><input type="checkbox" aria-label={`Select prediction ${p.id}`} checked={selected?.includes(p.id) ?? false} onChange={() => onSelect(p.id)} disabled={!p.eligible}/></td>}
    <td><Link className="match-cell" href={`/matches/${p.fixture.id}`}><span className="mini-teams"><TeamMark name={p.fixture.home} logo={p.fixture.home_logo}/><TeamMark name={p.fixture.away} logo={p.fixture.away_logo}/></span><span><strong>{p.fixture.home} <span className="muted vs">vs</span> {p.fixture.away}</strong><small>{p.fixture.competition} <span>·</span> {kickoff(p.fixture.kickoff)}</small></span></Link></td>
    <td><span className="market-cell">{p.market_label}</span></td><td><div className="probability-cell"><strong className={p.eligible ? "text-green" : ""}>{percent(p.probability, 1)}</strong><div className="probability-track"><span style={{width: percent(p.probability)}}/></div></div></td>
    <td className="odds-cell">{p.odds?.toFixed(2) ?? "—"}</td><td>{p.outcome !== "pending" ? <Badge tone={p.outcome === "won" ? "green" : p.outcome === "lost" ? "red" : "neutral"}>{readable(p.outcome)}</Badge> : p.eligible ? <Badge tone="green"><Check size={11}/> Eligible</Badge> : <Badge><Clock3 size={11}/> Below filter</Badge>}</td>
    <td><Link href={`/matches/${p.fixture.id}`} className="table-arrow" aria-label={`Analyze ${p.fixture.home} versus ${p.fixture.away}`}><ArrowUpRight size={17}/></Link></td>
  </tr>)}</tbody></table></div>;
}
