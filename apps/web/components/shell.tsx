"use client";
import { Activity, ArrowUpRight, BarChart3, BookOpen, ChevronDown, CircleHelp, Command, Crosshair, LayoutDashboard, Menu, Search, Settings2, ShieldCheck, Sparkles, Trophy, X, Zap } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useApi } from "@/hooks/use-api";
import { Overview } from "@/types/api";
import { cn } from "@/lib/utils";

const navigation = [
  {href: "/", label: "Overview", icon: LayoutDashboard}, {href: "/matches", label: "Match explorer", icon: Trophy},
  {href: "/predictions", label: "All predictions", icon: Crosshair},
  {href: "/predictions/high-confidence", label: "High confidence", icon: Zap},
  {href: "/booking-codes", label: "Booking codes", icon: BookOpen}, {href: "/performance", label: "Performance", icon: BarChart3},
];
export function Shell({children}: {children: React.ReactNode}) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const {data} = useApi<Overview>("/overview");
  return <div className="app-shell">
    <a href="#main" className="skip-link">Skip to content</a>
    {open && <button className="sidebar-overlay" aria-label="Close navigation" onClick={() => setOpen(false)}/>}
    <aside className={cn("sidebar", open && "sidebar-open")}>
      <Link href="/" className="brand" onClick={() => setOpen(false)}><span className="brand-symbol"><Activity size={24}/></span><span>sportpredict<span className="brand-ai">AI</span></span></Link>
      <button className="mobile-close icon-button" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={18}/></button>
      <div className="workspace-label"><span className="workspace-icon"><Command size={17}/></span><div>Football intelligence<small>Analytics workspace</small></div><ChevronDown size={14}/></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">{navigation.map(item => {
        const active = item.href === "/" ? pathname === "/" : item.href === "/predictions" ? pathname === item.href : pathname.startsWith(item.href);
        return <Link onClick={() => setOpen(false)} className={cn("nav-link", active && "nav-link-active")} aria-current={active ? "page" : undefined} href={item.href} key={item.href}><item.icon size={18}/>{item.label}{item.label === "High confidence" && <span className="nav-count">{data?.eligible_predictions ?? "—"}</span>}</Link>;
      })}</nav>
      <div className="nav-caption second-caption">PLATFORM</div>
      <nav aria-label="Platform navigation"><Link className={cn("nav-link", pathname === "/about" && "nav-link-active")} href="/about"><CircleHelp size={18}/> Methodology</Link><Link className={cn("nav-link", pathname.startsWith("/admin") && "nav-link-active")} href="/admin"><Settings2 size={18}/> Administration</Link></nav>
      <div className="sidebar-bottom"><div className="trust-panel"><ShieldCheck size={20}/><h3>Evidence over instinct.</h3><p>Every prediction has a model, a data trail, and a measurable outcome.</p><Link href="/about">How it works <ArrowUpRight size={14}/></Link></div><div className="sidebar-status"><span className={cn("status-dot", !data && "status-dot-off")}/>{data ? data.demo_mode ? "Demo environment" : data.data_mode === "personal_research" ? "Personal research feed" : "Authorized data feed" : "Connecting to API"}<span>v0.1</span></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu size={22}/></button><span className="breadcrumb">Workspace <span>/</span> <strong>{pathname.startsWith("/admin") ? "Administration" : navigation.find(n => n.href === pathname)?.label || "Match intelligence"}</strong></span></div><div className="topbar-right"><form className="global-search" onSubmit={e => {e.preventDefault(); router.push(`/matches?q=${encodeURIComponent(search)}`);}}><Search size={16}/><input aria-label="Quick search teams" placeholder="Search teams…" value={search} onChange={e => setSearch(e.target.value)}/><kbd>↵</kbd></form><span className="timezone">WAT <span>UTC+1</span></span><Link href="/admin" className="avatar" aria-label="Open administration">SP</Link></div></header>
      <main id="main">{data?.data_mode === "personal_research" && <div className="demo-banner"><ShieldCheck size={15}/><span><strong>Personal research data</strong> · sports-skills public feeds. Production and commercial use are disabled. Source coverage and freshness are not guaranteed.</span></div>}{children}</main><footer className="footer"><span>© {new Date().getFullYear()} SportPredict AI</span><span>Probabilities, never guarantees. 18+ · No automatic wagering.</span><Link href="/about">Our methodology <ArrowUpRight size={12}/></Link></footer>
    </div>
  </div>;
}
