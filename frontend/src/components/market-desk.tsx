"use client";

import { useEffect, useState } from "react";
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, CircleHelp, RefreshCw, ShieldAlert, Waves } from "lucide-react";
import { getMarketDesk, type MarketDesk as MarketDeskData, type MarketDeskPanel, type MarketIndicator } from "@/lib/api";

function fmtIndicator(item:MarketIndicator) {
  if(item.value===null || !Number.isFinite(item.value)) return "—";
  if(["WALCL","WRESBAL","WTREGEN"].includes(item.key)) return `$${(item.value/1_000_000).toLocaleString("en-US",{maximumFractionDigits:2})}tn`;
  if(item.key==="RRPONTSYD") return `$${item.value.toLocaleString("en-US",{maximumFractionDigits:1})}bn`;
  if(["CPIAUCSL","CPILFESL","PCEPI","PCEPILFE","UNRATE","PAYEMS","SOFR","EFFR","DGS2","DGS10","T10YIE","BAMLH0A0HYM2"].includes(item.key)) return `${item.value.toLocaleString("en-US",{maximumFractionDigits:2})}${item.key==="PAYEMS"?"k":"%"}`;
  if(item.key==="SOFR_EFFR") return `${item.value.toLocaleString("en-US",{maximumFractionDigits:1})}bp`;
  return item.value.toLocaleString("en-US",{maximumFractionDigits:2});
}
function dateLabel(date:string|null) { return date ? new Date(`${date}T12:00:00Z`).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"}) : "No observation"; }
function scoreTone(score:number|null) { return score===null?"text-slate-400":score>=60?"text-emerald-300":score<40?"text-rose-300":"text-amber-200"; }
function Arrow({direction}:{direction:string}) { const Icon=direction==="↑"?ArrowUpRight:direction==="↓"?ArrowDownRight:ArrowRight; return <Icon className="inline size-4" aria-hidden/>; }

function Why({indicator}:{indicator:MarketIndicator}) {
  return <details className="group mt-2 border-t border-white/[0.07] pt-2 text-xs text-slate-400">
    <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium text-slate-400 hover:text-slate-200"><CircleHelp className="size-3.5"/> WHY?</summary>
    <div className="mt-2 space-y-1.5 leading-relaxed">
      <p>{indicator.interpretation}</p><p>Current {fmtIndicator(indicator)} · Previous {fmtIndicator({...indicator,value:indicator.previous})} · Change {indicator.change===null?"—":`${indicator.change>0?"+":""}${indicator.change}`} · {indicator.frequency} · observed {dateLabel(indicator.as_of)} · {indicator.freshness}</p>
      <p>Source: {indicator.source_url?<a className="text-cyan-300 underline decoration-white/20 underline-offset-2" href={indicator.source_url} target="_blank" rel="noreferrer">{indicator.source}</a>:indicator.source}{indicator.reference_source_url&&<> · benchmark <a className="text-cyan-300 underline decoration-white/20 underline-offset-2" href={indicator.reference_source_url} target="_blank" rel="noreferrer">EFFR</a></>}. Score contribution: {indicator.score===null?"excluded (unavailable or stale)":`${indicator.score}/100`}.</p>
    </div>
  </details>;
}

function MetricRow({item}:{item:MarketIndicator}) {
  return <div className="py-3">
    <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="text-sm font-medium text-slate-200">{item.label}</div><div className="mt-1 text-[11px] text-slate-500">{item.as_of?`${dateLabel(item.as_of)} · ${item.freshness}`:"Data unavailable"}</div></div>
      <div className="shrink-0 text-right"><div className={`font-mono text-sm tabular-nums ${scoreTone(item.score)}`}>{fmtIndicator(item)}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">{item.signal}</div></div></div>
    <Why indicator={item}/>
  </div>;
}

function DeskCard({title,panel,icon:Icon}:{title:string;panel:MarketDeskPanel;icon:typeof Activity}) {
  return <section className="rounded-2xl border border-white/[0.09] bg-[#111a27] p-5 shadow-[0_18px_50px_-35px_rgba(0,0,0,.8)] sm:p-6">
    <div className="flex items-start justify-between gap-3"><div className="flex items-center gap-2.5"><div className="rounded-lg bg-white/[0.05] p-2 text-cyan-200"><Icon className="size-4"/></div><div><h3 className="text-xs font-semibold uppercase tracking-[.18em] text-slate-300">{title}</h3><p className="mt-1 text-[11px] text-slate-500">{panel.status} · {panel.coverage} signals</p></div></div><div className={`font-mono text-2xl font-medium tabular-nums ${scoreTone(panel.score)}`}>{panel.score===null?"—":Math.round(panel.score)}</div></div>
    <p className="mt-4 min-h-10 text-xs leading-relaxed text-slate-400">{panel.summary}</p>
    <div className="mt-2 divide-y divide-white/[0.06]">{panel.indicators.map(i=><MetricRow key={i.key} item={i}/>)}</div>
  </section>;
}

function MacroCard({data}:{data:MarketDeskData["macro"]}) {
  return <section className="rounded-2xl border border-white/[0.09] bg-[#111a27] p-5 shadow-[0_18px_50px_-35px_rgba(0,0,0,.8)] sm:p-6">
    <div className="flex items-start justify-between"><div><div className="flex items-center gap-2.5"><div className="rounded-lg bg-white/[0.05] p-2 text-cyan-200"><Activity className="size-4"/></div><h3 className="text-xs font-semibold uppercase tracking-[.18em] text-slate-300">Macro Desk</h3></div><p className="mt-4 text-xl font-semibold tracking-tight text-white">{data.regime}</p></div><span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] uppercase tracking-wider text-slate-400">{data.confidence}% confidence</span></div>
    <div className="mt-4 grid grid-cols-3 gap-2 text-xs"><div className="rounded-lg bg-white/[0.035] p-3"><div className="text-[10px] uppercase tracking-widest text-slate-500">Growth</div><div className="mt-1 capitalize text-slate-200">{data.growth}</div></div><div className="rounded-lg bg-white/[0.035] p-3"><div className="text-[10px] uppercase tracking-widest text-slate-500">Inflation</div><div className="mt-1 capitalize text-slate-200">{data.inflation}</div></div><div className="rounded-lg bg-white/[0.035] p-3"><div className="text-[10px] uppercase tracking-widest text-slate-500">Labour</div><div className="mt-1 capitalize text-slate-200">{data.labour}</div></div></div>
    <p className="mt-3 text-[11px] leading-relaxed text-slate-500">{data.method}</p><div className="mt-2 divide-y divide-white/[0.06]">{data.indicators.map(i=><MetricRow key={i.key} item={i}/>)}</div>
  </section>;
}

export function MarketDesk() {
  const [data,setData]=useState<MarketDeskData|null>(null); const [error,setError]=useState(false);
  useEffect(()=>{let active=true;getMarketDesk().then(d=>{if(active)setData(d)}).catch(()=>{if(active)setError(true)});return()=>{active=false}},[]);
  return <section className="overflow-hidden rounded-[26px] border border-white/[0.1] bg-[#0b111a] text-slate-100 shadow-[0_28px_90px_-48px_rgba(3,10,20,.9)]">
    <div className="border-b border-white/[0.07] px-5 py-4 sm:px-8"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[.24em] text-cyan-300">Tradefinder / Market Desk</p><p className="mt-1 text-xs text-slate-500">US market opening brief · deterministic, source-linked signals</p></div><div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500"><span className={`size-1.5 rounded-full ${data?"bg-emerald-400":"bg-amber-300"}`}/>{data?`Updated ${new Date(data.updated_at).toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit",timeZone:"UTC"})} UTC`:"Connecting to live sources"}</div></div></div>
    {error?<div className="m-5 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-5 text-sm text-amber-100">Market Desk is temporarily unavailable. Opportunities remain available below.</div>:<>
      <div className="grid gap-6 px-5 py-6 sm:px-8 sm:py-8 lg:grid-cols-[1.15fr_.85fr]">
        <div><div className="text-[10px] font-semibold uppercase tracking-[.22em] text-slate-500">US Market Regime</div><div className="mt-2 flex flex-wrap items-end gap-x-5 gap-y-2"><div className={`font-mono text-6xl font-medium leading-none tracking-[-.07em] tabular-nums sm:text-7xl ${scoreTone(data?.market_regime.score??null)}`}>{data?.market_regime.score===null||data?.market_regime.score===undefined?"—":Math.round(data.market_regime.score)}<span className="ml-1 text-2xl text-slate-600">/100</span></div><div className="pb-1"><div className="flex items-center gap-2 text-lg font-semibold tracking-wide text-white">{data?.market_regime.label??"Loading market data"}<Arrow direction={data?.market_regime.direction??"→"}/></div><div className="mt-1 text-xs text-slate-500">{data?.market_regime.status==="partial"?"PARTIAL DATA":"REGIME INDICATOR"} · confidence {data?.confidence??0}% · {data?.coverage.available??0}/{data?.coverage.expected??0} signals</div></div></div>
          <div className="mt-6 flex flex-wrap gap-2">{["Liquidity",data?.liquidity.status??"—","Stress",data?.stress.status??"—", "Growth",data?.macro.growth??"—","Inflation",data?.macro.inflation??"—"].map((x,i)=><span key={i} className={`rounded-full border px-3 py-1.5 text-[10px] uppercase tracking-wider ${i%2===0?"border-white/[0.08] bg-white/[0.025] text-slate-500":"border-cyan-300/10 bg-cyan-300/[0.04] text-slate-300"}`}>{x}</span>)}</div>
        </div>
        <div className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 sm:p-5"><div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.2em] text-slate-400"><Waves className="size-3.5 text-cyan-300"/> Desk call</div><div className="mt-3 space-y-2 text-sm leading-relaxed text-slate-200">{(data?.desk_call??["Retrieving official data sources. No market score is shown until valid observations are available."]).map((line,i)=><p key={i}>{line}</p>)}</div><p className="mt-4 text-[10px] text-slate-600">Conditions framework, not a prediction of future returns.</p></div>
      </div>
      <div className="grid gap-4 px-5 pb-5 sm:grid-cols-2 sm:px-8 sm:pb-8">{data?<><DeskCard title="Liquidity Desk" panel={data.liquidity} icon={Waves}/><DeskCard title="Stress Desk" panel={data.stress} icon={ShieldAlert}/><MacroCard data={data.macro}/><DeskCard title="Market Internals" panel={data.market_internals} icon={Activity}/></>:<div className="col-span-full rounded-xl border border-white/[0.07] p-5 text-sm text-slate-400"><RefreshCw className="mr-2 inline size-4 animate-spin"/>Loading sourced market observations…</div>}</div>
      {data&&<div className="grid gap-4 border-t border-white/[0.07] px-5 py-5 sm:grid-cols-3 sm:px-8 sm:py-6">
        <div><h3 className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.18em] text-slate-400"><ShieldAlert className="size-3.5 text-cyan-300"/> Cross-asset signals</h3><div className="mt-3 space-y-3">{data.cross_asset_signals.length?data.cross_asset_signals.map((s,i)=><div key={i}><div className="text-xs font-medium text-slate-200">{s.title}</div><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{s.detail}</p></div>):<p className="text-xs text-slate-500">No rule-based divergence detected in available series.</p>}</div></div>
        <div><h3 className="text-[10px] font-semibold uppercase tracking-[.18em] text-slate-400">What changed</h3><div className="mt-3 space-y-2">{data.what_changed.length?data.what_changed.slice(0,4).map((x,i)=><div key={i} className="flex justify-between gap-3 text-xs"><span className="text-slate-400">{x.label}<span className="ml-1.5 text-[9px] text-slate-600">{x.horizon}</span></span><span className="shrink-0 font-mono text-slate-200">{x.change>0?"+":""}{x.change}{x.unit}</span></div>):<p className="text-xs text-slate-500">No comparable changes available.</p>}</div></div>
        <div><h3 className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.18em] text-slate-400"><CalendarDays className="size-3.5 text-cyan-300"/> Watch next</h3><div className="mt-3 space-y-2">{data.watch_next.length?data.watch_next.map((x,i)=><div key={i} className="flex justify-between gap-3 text-xs"><span className="text-slate-300">{x.title}</span><span className="shrink-0 font-mono text-slate-500">{dateLabel(x.date)}</span></div>):<p className="text-xs text-slate-500">No upcoming release in the verified calendar feed.</p>}</div></div>
      </div>}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-5 py-3 text-[10px] text-slate-600 sm:px-8"><span>Sources: {data?.sources.join(" · ")||"waiting for sources"}. Each reading shows its observation date.</span><a href="/docs/MARKET_DESK.md" className="font-medium text-slate-400 underline decoration-white/15 underline-offset-2">Methodology & limitations</a></div>
    </>}
  </section>;
}
