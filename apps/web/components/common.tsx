"use client";
import { AlertCircle, ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Badge({children, tone = "neutral"}: {children: React.ReactNode; tone?: "green" | "amber" | "neutral" | "red"}) {
  return <span className={cn("badge", `badge-${tone}`)}>{children}</span>;
}
export function PageHeading({eyebrow, title, description, action}: {eyebrow?: string; title: string; description: string; action?: React.ReactNode}) {
  return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{description}</p></div>{action}</div>;
}
export function Loading() { return <div role="status" aria-label="Loading data" className="loading-grid">{[1,2,3,4].map(n => <div className="skeleton" key={n} />)}<span className="sr-only">Loading data…</span></div>; }
export function ErrorState({error, retry}: {error: Error; retry?: () => void}) { return <div className="empty-state" role="alert"><AlertCircle size={30}/><h3>We couldn’t load this data</h3><p>{error.message}</p>{retry && <Button variant="outline" onClick={retry}><RefreshCw size={15}/> Try again</Button>}</div>; }
export function Empty({title, description}: {title: string; description: string}) { return <div className="empty-state"><ShieldCheck size={30}/><h3>{title}</h3><p>{description}</p></div>; }
export function SectionTitle({title, description, href, label = "View all"}: {title: string; description?: string; href?: string; label?: string}) {
  return <div className="section-title"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{href && <Link href={href} className="text-link">{label} <ArrowUpRight size={15}/></Link>}</div>;
}
export function TeamMark({name, logo, size = "normal"}: {name: string; logo?: string | null; size?: "normal" | "large"}) {
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => setImageFailed(false), [logo]);
  const colors = ["#8cacf5", "#c8a5ed", "#e6b985", "#8ccebb", "#dc9292", "#b4c6d3"];
  const hash = [...name].reduce((v,c) => v + c.charCodeAt(0), 0);
  return <span className={cn("team-mark", logo && !imageFailed && "team-mark-with-logo", size === "large" && "team-mark-large")} style={{color: colors[hash % colors.length]}} aria-hidden="true">{logo && !imageFailed ? <img src={logo} alt="" loading="lazy" onError={() => setImageFailed(true)}/> : name.split(" ").slice(0,2).map(w => w[0]).join("")}</span>;
}
