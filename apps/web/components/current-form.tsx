"use client";
import { useApi } from "@/hooks/use-api";
import { kickoff, readable } from "@/lib/api";
import { SectionTitle } from "@/components/common";
import type { Fixture, Prediction } from "@/types/api";

export function CurrentForm({id}: {id: number}) {
  const result = useApi<{fixture: Fixture; predictions: Prediction[]; evidence?: Prediction["features"] | null}>(`/fixtures/${id}`);
  const data = result.data;
  if (!data?.evidence || data.predictions.length) return null;
  const evidence = data.evidence;
  return <section className="panel">
    <SectionTitle title="Current team form" description="Observed historical results. These are context, not model probabilities."/>
    <div className="form-comparison">{[[data.fixture.home, evidence.home_form], [data.fixture.away, evidence.away_form]].map(([name, form]) => <div key={String(name)}>
      <strong>{String(name)}</strong><div>{(form as string[]).map((value, index) => <span className={`form-result form-${value.toLowerCase()}`} key={index}>{value}</span>)}</div>
    </div>)}</div>
    <div className="feature-list">{Object.entries(evidence.values).map(([name, value]) => <div key={name}><span>{readable(name)}</span><strong>{value.toFixed(2)}</strong></div>)}</div>
    <p className="panel-bottom">Evidence as of {kickoff(evidence.as_of + "Z")} WAT. A trained and approved model is required before showing calibrated probabilities.</p>
  </section>;
}
