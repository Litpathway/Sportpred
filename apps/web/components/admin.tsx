"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowRight, Check, Database, FileSpreadsheet, KeyRound, LoaderCircle, LogOut, Pause, Play, RefreshCw, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { useApi } from "@/hooks/use-api";
import { api, ApiError, kickoff, percent, readable } from "@/lib/api";
import { Badge, Empty, ErrorState, Loading, PageHeading, SectionTitle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { PredictionTable } from "@/components/prediction-table";
import type { AdminUser, Audit, Fixture, Job, Model, Overview, Page, PlatformSettings, Prediction, Providers, Slip } from "@/types/api";
import { cn } from "@/lib/utils";

const loginSchema = z.object({email: z.email("Enter a valid email address"), password: z.string().min(1,"Enter your password")});
export function LoginView() {
  const router = useRouter(); const client = useQueryClient(); const [error,setError] = useState("");
  const [ready,setReady] = useState(false);
  useEffect(() => setReady(true), []);
  const {register,handleSubmit,formState:{errors,isSubmitting}} = useForm<z.infer<typeof loginSchema>>({resolver:zodResolver(loginSchema)});
  return <div className="login-wrap"><div className="panel login-panel"><span className="login-icon"><KeyRound size={25}/></span><div className="eyebrow">ADMINISTRATION</div><h1>Welcome to the control room.</h1><p>Sign in to manage data, models and publication.</p><form onSubmit={handleSubmit(async values => {setError("");try {const user = await api<AdminUser>("/auth/login",{method:"POST",body:JSON.stringify(values)});client.setQueryData(["/auth/me"],user);router.push("/admin");} catch(e) {setError((e as Error).message);}})}>
  <fieldset disabled={!ready || isSubmitting}><label>Email address<input autoComplete="username" type="email" {...register("email")}/></label>{errors.email && <small className="field-error">{errors.email.message}</small>}
  <label>Password<input autoComplete="current-password" type="password" {...register("password")}/></label>{errors.password && <small className="field-error">{errors.password.message}</small>}{error && <div className="form-error" role="alert">{error}</div>}<Button type="submit" disabled={isSubmitting}>{isSubmitting ? <LoaderCircle className="spin" size={16}/> : <ArrowRight size={16}/>} Sign in</Button></fieldset></form><div className="login-note"><ShieldCheck size={15}/> Role-based access · Secure session cookies</div><p className="footnote">Use the admin account created with the setup command. Credentials are never supplied by the frontend.</p></div></div>;
}

const adminSections = [
  {key:"overview",label:"Overview",title:"Admin overview",description:"Check system health, recent work and the actions that need attention."},
  {key:"fixtures",label:"Fixtures",title:"Fixture data",description:"Review imported matches and the freshness of provider updates."},
  {key:"predictions",label:"Predictions",title:"Prediction review",description:"Review model outputs and select eligible predictions for publication."},
  {key:"codes",label:"Publications",title:"Publications",description:"Review candidate slips, verification status and publishing outcomes."},
  {key:"models",label:"Models & data",title:"Models and training data",description:"Import historical results, train a model and review its holdout performance."},
  {key:"providers",label:"Data providers",title:"Data providers",description:"Check provider connections, data freshness and recent sync warnings."},
  {key:"settings",label:"Settings",title:"Platform settings",description:"Manage publication and quality controls. Changes are recorded in the audit trail."},
] as const;
const quickActions = [
  {key:"sync",label:"Sync fixture data",icon:RefreshCw},
  {key:"train",label:"Train model",icon:Sparkles},
  {key:"predict",label:"Generate predictions",icon:Play},
  {key:"pipeline",label:"Run publication pipeline",icon:RefreshCw},
  {key:"settle",label:"Settle finished matches",icon:Check},
];
export function AdminView({path}: {path:string}) {
  const user = useApi<AdminUser>("/auth/me"); const router = useRouter(); const client = useQueryClient();
  const [message,setMessage] = useState(""); const [failed,setFailed] = useState(false); const [busy,setBusy] = useState("");
  useEffect(() => {if(user.error instanceof ApiError && user.error.status===401) router.replace("/login");},[user.error,router]);
  const requestedSection = path.split("/")[2] || "overview";
  const activeSection = adminSections.find(item => item.key === requestedSection) || adminSections[0];
  const section = activeSection.key;
  const mutate = async (endpoint:string,body:unknown,method="POST") => {
    if(!user.data) return;
    setBusy(endpoint);setMessage("");setFailed(false);
    try {const result = await api<Record<string,unknown>>(endpoint,{method,headers:{"X-CSRF-Token":user.data.csrf_token},body:JSON.stringify(body)});setMessage("status" in result && result.status==="queued" ? "Action queued. Follow its progress in the Background jobs list." : "Changes saved.");await client.invalidateQueries();return result;}catch(e){setMessage((e as Error).message);setFailed(true);}finally{setBusy("");}
  };
  if(user.isPending || user.error instanceof ApiError && user.error.status===401) return <Loading/>;
  if(user.error) return <ErrorState error={user.error} retry={() => user.refetch()}/>;
  const canWrite = user.data?.role!=="viewer"; const isAdmin = user.data?.role==="admin";
  const actionsForSection = section === "overview" ? quickActions
    : section === "models" ? quickActions.filter(action => action.key === "train")
    : section === "fixtures" || section === "providers" ? quickActions.filter(action => action.key === "sync")
    : section === "predictions" ? quickActions.filter(action => action.key === "predict")
    : section === "codes" ? quickActions.filter(action => action.key === "pipeline") : [];
  return <>
    <PageHeading eyebrow="ADMINISTRATION" title={activeSection.title} description={activeSection.description} action={<div className="admin-user"><div className="admin-user-details"><ShieldCheck size={17}/><span>{user.data?.email}<small>{isAdmin ? "Administrator" : canWrite ? "Operator" : "Read only"}</small></span></div><Button variant="outline" onClick={async () => {const result=await mutate("/auth/logout",{});if(result){client.clear();router.push("/login");}}}><LogOut size={15}/>Sign out</Button></div>}/>
    <nav className="tabs admin-tabs" aria-label="Admin sections">{adminSections.map(tab => <Link aria-current={section===tab.key?"page":undefined} className={cn(section===tab.key&&"active")} key={tab.key} href={tab.key==="overview" ? "/admin" : "/admin/"+tab.key}>{tab.label}</Link>)}</nav>
    {message && <div role={failed?"alert":"status"} className={cn("notice",failed&&"notice-error")}>{failed ? null : <Check size={15}/>} {message}</div>}
    {canWrite && actionsForSection.length>0 && <section className="panel admin-quick-actions" aria-labelledby="quick-actions-title"><div className="admin-quick-copy"><h2 id="quick-actions-title">{section==="overview"?"Quick actions":section==="models"?"Model training":"Page actions"}</h2><p>{section==="overview"?"Start a task, then follow its status in Background jobs below.":section==="models"?"Training creates a version for review. It does not approve the model or publish predictions.":"Start the relevant task and check its progress in the overview."}</p></div><div className="admin-action-buttons" role="group" aria-label="Administrative actions">{actionsForSection.map(action=>{const Icon=action.icon;const isBusy=busy.endsWith(action.key);return <Button size="sm" variant={action.key==="train"?"default":"outline"} key={action.key} disabled={!!busy} aria-busy={isBusy} onClick={()=>mutate("/admin/jobs/"+action.key,{})}>{isBusy?<LoaderCircle size={14} className="spin"/>:<Icon size={14}/>} {isBusy?"Working...":action.label}</Button>;})}</div>{section==="overview"&&<p className="admin-action-note"><strong>Important:</strong> Run publication pipeline does not train or approve a model. Train and review a model from Models &amp; data first.</p>}</section>}
    {section==="overview" && <AdminOverview/>}{section==="fixtures" && <AdminFixtures/>}{section==="predictions" && <AdminPredictions canWrite={canWrite} busy={!!busy} mutate={mutate}/>}{section==="codes" && <AdminCodes/>}{section==="models" && <AdminModels canApprove={isAdmin} canUpload={isAdmin} busy={!!busy} csrfToken={user.data?.csrf_token||""} mutate={mutate}/>}{section==="providers" && <AdminProviders/>}{section==="settings" && <SettingsForm canWrite={isAdmin} busy={!!busy} mutate={mutate}/>}
  </>;
}
type Mutate = (endpoint:string,body:unknown,method?:string) => Promise<Record<string,unknown> | undefined>;
function AdminOverview() {
  const overview = useApi<Overview & {failed_jobs:number}>("/admin/overview"); const jobs = useApi<Job[]>("/admin/jobs"); const audit = useApi<Audit[]>("/admin/audit");
  if(overview.isPending) return <Loading/>;if(overview.error) return <ErrorState error={overview.error}/>;
  const o=overview.data!;
  return <>
    <div className="admin-summary" aria-label="Platform status">
      <Link href="/admin/settings" className="panel admin-status-card"><small>Publication</small><strong>{o.publication_paused?"Paused":"Active"}</strong><Badge tone={o.publication_paused?"amber":"green"}>{o.publication_paused?"Paused":"Accepting eligible predictions"}</Badge><span>Review publication controls</span></Link>
      <Link href="/admin/models" className="panel admin-status-card"><small>Model status</small><strong>{o.model?.approved?"Approved":o.model?"Awaiting approval":"Not trained"}</strong><Badge tone={o.model?.simulated?"amber":o.model?.approved?"green":"neutral"}>{o.model?.simulated?"Simulated data":o.model?"Historical data":"No model available"}</Badge><span>{o.model?.version||"Open Models & data to import history or train."}</span></Link>
      <Link href="/admin/fixtures" className="panel admin-status-card"><small>Upcoming fixtures</small><strong>{o.upcoming_matches}</strong><span>Across {o.competitions} competitions. Review fixture data.</span></Link>
      <Link href="#background-jobs" className="panel admin-status-card"><small>Failed background jobs</small><strong>{o.failed_jobs}</strong><Badge tone={o.failed_jobs?"red":"green"}>{o.failed_jobs?"Needs attention":"No failed jobs"}</Badge><span>View recent job activity</span></Link>
    </div>
    <section className="panel" id="background-jobs"><SectionTitle title="Background jobs" description="Queued work runs in the background. Check status and errors here."/>{jobs.isPending ? <Loading/> : jobs.error ? <ErrorState error={jobs.error}/> : jobs.data?.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Activity</th><th>Status</th><th>Attempts</th><th>Last started</th><th>Latest error</th></tr></thead><tbody>{jobs.data.map(j => <tr key={j.id}><td>{readable(j.name)}</td><td><Badge tone={j.status==="succeeded"?"green":j.status==="dead_letter"?"red":"amber"}>{readable(j.status)}</Badge></td><td>{j.attempts}</td><td>{kickoff(j.started_at)}</td><td>{j.error || "-"}</td></tr>)}</tbody></table></div> : <Empty title="No background activity yet" description="Choose a quick action above. Its status will appear here."/>}</section>
    <section className="panel"><SectionTitle title="Recent activity" description="A record of changes and system actions."/>{audit.isPending ? <Loading/> : audit.error ? <ErrorState error={audit.error}/> : audit.data?.length ? <div className="audit-list">{audit.data.map(a => <details key={a.id}><summary><span>{readable(a.action)}<small>{a.actor||"System"} / {a.entity}</small></span><time>{kickoff(a.created_at)}</time></summary><pre>{JSON.stringify(a.detail,null,2)}</pre></details>)}</div> : <Empty title="No activity recorded" description="Admin actions will appear here when they occur."/>}</section>
  </>;
}
function AdminFixtures() {
  const result=useApi<Page<Fixture>>("/fixtures?status=all&limit=100");
  if(result.isPending)return <Loading/>;if(result.error)return <ErrorState error={result.error}/>;
  return <section className="panel"><SectionTitle title="Fixture ingestion" description={`First 100 of ${result.data?.total} fixtures. Provider timestamps are stored in UTC.`}/><div className="table-scroll"><table className="data-table"><thead><tr><th>Fixture</th><th>Kickoff · WAT</th><th>Status</th><th>Source</th><th>Refreshed</th></tr></thead><tbody>{result.data?.items.map(f=><tr key={f.id}><td><Link href={`/matches/${f.id}`}>{f.home} vs {f.away}</Link><small>{f.competition}</small></td><td>{kickoff(f.kickoff)}</td><td>{readable(f.status)}</td><td><Badge tone={f.simulated?"amber":"neutral"}>{f.simulated?"Simulated":"Provider feed"}</Badge></td><td>{kickoff(f.synced_at)}</td></tr>)}</tbody></table></div></section>;
}
function AdminPredictions({canWrite,busy,mutate}:{canWrite:boolean;busy:boolean;mutate:Mutate}) {
  const result=useApi<Page<Prediction>>("/predictions?limit=100");const [selected,setSelected]=useState<number[]>([]);
  if(result.isPending)return <Loading/>;if(result.error)return <ErrorState error={result.error}/>;
  return <section className="panel"><SectionTitle title="Prediction review" description="Select eligible predictions to create a candidate slip. Default maximum: one leg."/>{canWrite&&<div className="panel-toolbar"><span>{selected.length} selected</span><Button size="sm" disabled={!selected.length||busy} onClick={async()=>{const result=await mutate("/admin/slips",{prediction_ids:selected});if(result)setSelected([]);}}>Create candidate slip</Button></div>}{result.data?.items.length?<PredictionTable items={result.data.items} selected={selected} onSelect={canWrite?id=>setSelected(selected.includes(id)?selected.filter(i=>i!==id):[...selected,id]):undefined}/>:<Empty title="No predictions" description="Train and approve a model, then generate predictions."/>}</section>;
}
function AdminCodes() {
  const result=useApi<Slip[]>("/admin/slips");if(result.isPending)return <Loading/>;if(result.error)return <ErrorState error={result.error}/>;
  return <section className="panel"><SectionTitle title="Candidate slips & publications" description="Genuine codes are displayed only after exact-selection verification."/>{result.data?.length?<div className="table-scroll"><table className="data-table"><thead><tr><th>ID</th><th>Status</th><th>Legs</th><th>Probability</th><th>Code</th><th>Verification</th><th>Reason</th></tr></thead><tbody>{result.data.map(s=><tr key={s.id}><td>{s.published_at?<Link href={`/booking-codes/${s.id}`}>#{s.id}</Link>:`#${s.id}`}</td><td>{readable(s.status)}</td><td>{s.predictions.length}</td><td>{percent(s.joint_probability,1)}</td><td>{s.code || "—"}</td><td><Badge tone={s.verified?"green":"neutral"}>{s.verified?"Verified":"No verified code"}</Badge></td><td>{s.failure_reason||s.assumption}</td></tr>)}</tbody></table></div>:<Empty title="No slips yet" description="Select an eligible prediction or run the publication pipeline."/>}</section>;
}
function AdminModels({canApprove,canUpload,busy,csrfToken,mutate}:{canApprove:boolean;canUpload:boolean;busy:boolean;csrfToken:string;mutate:Mutate}) {
  const result=useApi<Model[]>("/admin/models");if(result.isPending)return <Loading/>;if(result.error)return <ErrorState error={result.error}/>;
  return <>
    <section className="panel admin-training-panel"><SectionTitle title="Historical match data" description="Import completed results to provide the evidence used during training."/><CsvTrainingUpload enabled={canUpload} csrfToken={csrfToken}/><div className="admin-training-guidance"><FileSpreadsheet size={17}/><div><strong>CSV format</strong><p>Required columns: Div, Date, HomeTeam, AwayTeam, FTHG, FTAG. Dates without a time are read as 12:00 UTC. Upload data you are licensed to use; imported result-availability times are estimates.</p></div></div></section>
    <div className="admin-model-intro"><div><h2>Trained model versions</h2><p>Training creates a version for review. It is not used for public predictions until an administrator approves it.</p></div><Badge tone={result.data?.some(model=>model.approved)?"green":"amber"}>{result.data?.some(model=>model.approved)?"Approved model available":"Approval required"}</Badge></div>
    {result.data?.length?result.data.map(m=><section className="panel model-card" key={m.id}><div className="section-title"><div><Badge tone={m.simulated?"amber":"neutral"}>{m.simulated?"Simulated data":"Historical data"}</Badge><h2>{m.version}</h2><p>{m.metrics.algorithm}</p></div>{canApprove&&<Button variant={m.approved?"outline":"default"} disabled={busy} onClick={()=>mutate("/admin/models/"+m.id+"/approval",{approved:!m.approved},"PUT")}>{m.approved?<Pause size={14}/>:<ShieldCheck size={14}/>} {m.approved?"Revoke approval":"Approve version"}</Button>}</div><div className="detail-grid"><div><small>Training fixtures</small><strong>{m.metrics.training_rows}</strong></div><div><small>Validation fixtures</small><strong>{m.metrics.validation_rows}</strong></div><div><small>Test fixtures</small><strong>{m.metrics.test_rows}</strong></div><div><small>Test Brier score</small><strong>{m.metrics.brier.toFixed(3)}</strong></div><div><small>Test log loss</small><strong>{m.metrics.log_loss.toFixed(3)}</strong></div><div><small>Approval status</small><strong>{m.approved?"Approved":"Awaiting review"}</strong></div><div><small>Data period</small><strong>{kickoff(m.trained_until)}</strong></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Market</th><th>Test fixtures</th><th>Brier score</th><th>Log loss</th><th>Accuracy</th></tr></thead><tbody>{Object.entries(m.metrics.markets).map(([name,value])=><tr key={name}><td>{readable(name)}</td><td>{value.n}</td><td>{value.brier.toFixed(3)}</td><td>{value.log_loss.toFixed(3)}</td><td>{percent(value.accuracy,1)}</td></tr>)}</tbody></table></div><p className="footnote">Calibration is fitted on validation data. Test data is held back from model fitting. Simulated results are not evidence of real-world performance.</p></section>):<Empty title="No trained versions yet" description="Import enough historical matches, select Train model, then review the test metrics here before approval."/>}
  </>;
}

function CsvTrainingUpload({enabled,csrfToken}:{enabled:boolean;csrfToken:string}) {
  const client=useQueryClient();const inputRef=useRef<HTMLInputElement>(null);const [file,setFile]=useState<File|null>(null);const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [failed,setFailed]=useState(false);
  const selectFile=(selected:File|undefined)=>{setFailed(false);setMessage("");if(selected&&selected.size>3_000_000){setFile(null);setFailed(true);setMessage("This CSV is larger than 3 MB. Choose a smaller file.");if(inputRef.current)inputRef.current.value="";return;}setFile(selected||null);};
  const submit=async()=>{if(!file||!enabled)return;setBusy(true);setMessage("");setFailed(false);try{const form=new FormData();form.append("file",file);const response=await fetch("/api/admin/training-data/csv",{method:"POST",credentials:"same-origin",headers:{"X-CSRF-Token":csrfToken},body:form});const body=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof body.detail==="string"?body.detail:"CSV upload failed");setMessage("Imported "+body.rows+" matches: "+body.created+" new and "+body.updated+" updated. Results are used only after a 24-hour availability delay.");setFile(null);if(inputRef.current)inputRef.current.value="";await client.invalidateQueries();}catch(e){setFailed(true);setMessage((e as Error).message);}finally{setBusy(false);}};
  return <div className="csv-upload"><label htmlFor="training-csv" className={cn("csv-file",!enabled&&"csv-file-disabled")}><span className="csv-file-icon"><FileSpreadsheet size={18}/></span><span className="csv-file-copy"><strong>{file?.name||"Choose a results CSV"}</strong><small>{file?Math.ceil(file.size/1024)+" KB selected":"UTF-8 CSV file, up to 3 MB"}</small></span><span className="csv-browse">Browse</span></label><input ref={inputRef} className="sr-only" id="training-csv" type="file" accept=".csv,text/csv" disabled={!enabled||busy} aria-describedby="training-csv-help" onChange={e=>selectFile(e.target.files?.[0])}/><p id="training-csv-help" className="csv-help">Expected columns: Div, Date, HomeTeam, AwayTeam, FTHG and FTAG.</p><Button size="sm" disabled={!enabled||!file||busy} onClick={submit}>{busy?<LoaderCircle size={14} className="spin"/>:<Upload size={14}/>} {busy?"Importing...":"Import match history"}</Button>{!enabled&&<small className="csv-permission">Administrator access is required to upload training data.</small>}{message&&<span role={failed?"alert":"status"} className={cn("csv-message",failed&&"field-error")}>{message}</span>}</div>;
}
function AdminProviders() {
  const result=useApi<Providers>("/admin/providers");if(result.isPending)return <Loading/>;if(result.error)return <ErrorState error={result.error}/>;
  const p=result.data!;
  return <div className="analysis-grid"><section className="panel provider-card"><Database size={25}/><h2>Fixture provider</h2><Badge tone={p.fixtures.status==="fresh"?"green":"amber"}>{readable(p.fixtures.status)}</Badge><dl><dt>Adapter</dt><dd>{p.fixtures.name}</dd><dt>Enabled</dt><dd>{p.fixtures.enabled?"Yes":"No"}</dd><dt>Last successful sync</dt><dd>{p.fixtures.last_sync?kickoff(p.fixtures.last_sync):"Never"}</dd></dl><p>Fixture, odds and enrichment payloads share the validated feed contract. Toggle ingestion in Settings.</p></section><section className="panel provider-card"><ShieldCheck size={25}/><h2>Booking-code provider</h2><Badge tone={p.booking.genuine_enabled?"green":"neutral"}>{p.booking.genuine_enabled?"Genuine integration configured":"Prediction-only mode"}</Badge><dl><dt>Adapter</dt><dd>{p.booking.name}</dd><dt>Recent failed jobs</dt><dd>{p.recent_failure_count}</dd></dl><p>Authorized gateway credentials are configured on the server. Mock and unavailable adapters cannot publish genuine codes.</p></section></div>;
}
const settingsSchema=z.object({threshold:z.number().min(.5).max(.99),min_quality:z.number().min(.5).max(1),max_legs:z.number().int().min(1).max(3),publication_paused:z.boolean(),provider_enabled:z.boolean()});
function SettingsForm({canWrite,busy,mutate}:{canWrite:boolean;busy:boolean;mutate:Mutate}) {
  const result=useApi<PlatformSettings>("/admin/settings");const {register,reset,handleSubmit,formState:{errors}}=useForm<PlatformSettings>({resolver:zodResolver(settingsSchema)});
  useEffect(()=>{if(result.data)reset(result.data);},[result.data,reset]);
  if(result.isPending)return <Loading/>;if(result.error)return <ErrorState error={result.error}/>;
  return <section className="panel settings-panel"><SectionTitle title="Publication & quality controls" description="Changes are audited and trigger a fresh eligibility check."/><form onSubmit={handleSubmit(values=>mutate("/admin/settings",values,"PUT"))}><fieldset disabled={!canWrite||busy}><label>Minimum probability<input type="number" step="0.01" min="0.5" max="0.99" {...register("threshold",{valueAsNumber:true})}/><small>Default 0.80. A calibrated estimate, not a guarantee.</small>{errors.threshold&&<span className="field-error">{errors.threshold.message}</span>}</label><label>Minimum data quality<input type="number" step="0.01" min="0.5" max="1" {...register("min_quality",{valueAsNumber:true})}/>{errors.min_quality&&<span className="field-error">{errors.min_quality.message}</span>}</label><label>Maximum slip legs<input type="number" min="1" max="3" {...register("max_legs",{valueAsNumber:true})}/><small>Single selections by default. Multi-leg joint probabilities are withheld.</small></label><label className="checkbox-label"><input type="checkbox" {...register("publication_paused")}/><span>Pause automatic publication</span></label><label className="checkbox-label"><input type="checkbox" {...register("provider_enabled")}/><span>Enable fixture-provider ingestion</span></label><Button type="submit" disabled={busy}>{busy?<LoaderCircle className="spin" size={15}/>:<Check size={15}/>}Save settings</Button></fieldset></form>{!canWrite&&<p className="footnote">Your role can inspect settings. An administrator must approve changes.</p>}</section>;
}
