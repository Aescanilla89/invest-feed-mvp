const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://invest-feed-mvp.onrender.com/api";
export type RiskBucket = "bajo" | "medio" | "alto" | "desconocido";
export interface Weinstein { stage: 1 | 2 | 3 | 4; is_transition: boolean; weeks_in_stage: number; ma_slope_pct: number; relative_volume: number; rsi: number; }
export interface CanslimCriterion { value: boolean | null; detail: string; }
export interface Canslim { criteria: Record<string, CanslimCriterion>; score: string; }
export type SignalType = "weinstein" | "canslim" | "both" | null;
export type StrategyName = "minervini" | "lynch" | "berkshire" | "dividendos";
export interface StrategyResult { passed: boolean | null; score: number | null; details: string; }
export interface Opportunity { ticker: string; name: string | null; sector: string | null; combined_score: number; risk_bucket: RiskBucket; weinstein: Weinstein; canslim: Canslim; explanation: string | null; last_updated: string; first_detected_date?: string | null; first_detected_price?: number | null; current_price?: number | null; return_since_first_detected_pct?: number | null; signal_type?: SignalType; strategies: Partial<Record<StrategyName, StrategyResult>>; selection_score?: number | null; selection_method?: string | null; }
export interface PriceBar { date: string; open: number; high: number; low: number; close: number; volume: number; }
export interface OpportunityDetail extends Opportunity { price_history: PriceBar[]; }
export interface OpportunityFilters { risk?: RiskBucket; sector?: string; strategy?: StrategyName | "weinstein" | "canslim" | "early_stage2"; limit?: number; offset?: number; }
export interface MarketIndicator { key:string; label:string; value:number|null; previous:number|null; change:number|null; change_1w?:number|null; change_1m?:number|null; as_of:string|null; frequency:string; freshness:string; source:string; source_url:string|null; reference_source_url?:string|null; interpretation:string; signal:string; score:number|null; weight:number; }
export interface MarketDeskPanel { score:number|null; status:string; summary:string; indicators:MarketIndicator[]; coverage:number; }
export interface MarketDesk { market_regime:{score:number|null;label:string;direction:string;status:string;components:Record<string,number|null>;method:string}; liquidity:MarketDeskPanel; stress:MarketDeskPanel; macro:{regime:string;growth:string;inflation:string;labour:string;confidence:number;indicators:MarketIndicator[];method:string}; market_internals:MarketDeskPanel; cross_asset_signals:Array<{level:string;title:string;detail:string}>; desk_call:string[]; what_changed:Array<{label:string;change:number;unit:string;horizon:string;as_of:string;source:string}>; watch_next:Array<{date:string;title:string;source:string;consensus:number|null}>; confidence:number; coverage:{available:number;expected:number}; sources:string[]; updated_at:string; }
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
const responseCache = new Map<string, { expires: number; value: unknown }>();
const pendingRequests = new Map<string, Promise<unknown>>();
const CACHE_TTL = 60_000;
async function fetchJson<T>(path: string): Promise<T> {
  const browser = typeof window !== "undefined";
  const cached = browser ? responseCache.get(path) : undefined;
  if (cached && cached.expires > Date.now()) return cached.value as T;
  const pending = browser ? pendingRequests.get(path) : undefined;
  if (pending) return pending as Promise<T>;
  const request = (async () => {
    const res = await fetch(API_BASE_URL + path, { next: { revalidate: 60 } });
    if (!res.ok) throw new Error("Error " + res.status + " consultando " + path);
    const value = await res.json() as T;
    if (browser) {
      for (const [key, entry] of responseCache) if (entry.expires <= Date.now()) responseCache.delete(key);
      if (responseCache.size >= 100) responseCache.delete(responseCache.keys().next().value!);
      responseCache.set(path, { expires: Date.now() + CACHE_TTL, value });
    }
    return value;
  })();
  if (browser) pendingRequests.set(path, request);
  try { return await request; } finally { if (browser) pendingRequests.delete(path); }
}
export async function getOpportunities(filters: OpportunityFilters = {}): Promise<Opportunity[]> {
  if (DEMO_MODE) {
    const { DEMO_OPPORTUNITIES } = await import("./demo-data");
    let result = [...DEMO_OPPORTUNITIES];
    if (filters.risk) result = result.filter((o) => o.risk_bucket === filters.risk);
    if (filters.sector) result = result.filter((o) => o.sector === filters.sector);
    if (filters.strategy === "early_stage2") return result.filter((o) => o.weinstein.stage === 2 && o.weinstein.weeks_in_stage <= 6).sort((a, b) => a.weinstein.weeks_in_stage - b.weinstein.weeks_in_stage);
    return result.sort((a, b) => b.combined_score - a.combined_score);
  }
  const params = new URLSearchParams();
  if (filters.risk) params.set("risk", filters.risk);
  if (filters.sector) params.set("sector", filters.sector);
  if (filters.strategy) params.set("strategy", filters.strategy);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  const query = params.toString();
  return fetchJson<Opportunity[]>("/opportunities" + (query ? "?" + query : ""));
}
export async function getOpportunityDetail(symbol: string): Promise<OpportunityDetail> {
  if (DEMO_MODE) {
    const { getDemoDetail } = await import("./demo-data");
    const detail = getDemoDetail(symbol);
    if (!detail) throw new Error("Ticker " + symbol + " no existe en el set de demo");
    return detail;
  }
  return fetchJson<OpportunityDetail>("/opportunities/" + symbol);
}
export type CatalystType = "earnings" | "insider_buy" | "macro_data";
export type CatalystClassification = "oro" | "plata" | "bronce";
export interface Catalyst { id: number; ticker: string | null; company_name: string | null; sector: string | null; catalyst_type: CatalystType; title: string; description: string | null; detected_date: string; extra: Record<string, unknown>; combined_score: number | null; classification: CatalystClassification | null; explanation: string | null; }
export async function getCatalysts(days = 7): Promise<Catalyst[]> {
  if (DEMO_MODE) { const { DEMO_CATALYSTS } = await import("./demo-data"); return DEMO_CATALYSTS; }
  return fetchJson<Catalyst[]>("/catalysts?days=" + days);
}
export async function getMarketDesk(): Promise<MarketDesk> { return fetchJson<MarketDesk>("/market-desk"); }
