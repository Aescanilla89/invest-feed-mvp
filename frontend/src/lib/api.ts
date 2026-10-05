const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "https://invest-feed-mvp.onrender.com/api";

export type RiskBucket = "bajo" | "medio" | "alto" | "desconocido";

export interface Weinstein {
  stage: 1 | 2 | 3 | 4;
  is_transition: boolean;
  weeks_in_stage: number;
  ma_slope_pct: number;
  relative_volume: number;
  rsi: number;
}

export interface CanslimCriterion {
  value: boolean | null;
  detail: string;
}

export interface Canslim {
  criteria: Record<string, CanslimCriterion>;
  score: string;
}

export type SignalType = "weinstein" | "canslim" | "both" | null;

export type StrategyName = "minervini" | "lynch" | "berkshire" | "dividendos";

export interface StrategyResult {
  passed: boolean | null;
  score: number | null;
  details: string;
}

export interface Opportunity {


// Historical performance fields returned by the detail endpoint.
export interface OpportunityDetailPerformance {
  first_detected_price?: number | null;
  current_price?: number | null;
  return_since_first_detected_pct?: number | null;
}
  ticker: string;
  name: string | null;
  sector: string | null;
  combined_score: number;
  risk_bucket: RiskBucket;
  weinstein: Weinstein;
  canslim: Canslim;
  explanation: string | null;
  last_updated: string;
  first_detected_date?: string | null;
  signal_type?: SignalType;
  strategies: Partial<Record<StrategyName, StrategyResult>>;
  selection_score?: number | null;
  selection_method?: string | null;
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OpportunityDetail extends Opportunity {
  price_history: PriceBar[];
}

export interface OpportunityFilters {
  risk?: RiskBucket;
  sector?: string;
  strategy?: StrategyName | "weinstein" | "canslim" | "early_stage2";
  limit?: number;
  offset?: number;
}

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

const responseCache = new Map<string, { expires: number; value: unknown }>();
const pendingRequests = new Map<string, Promise<unknown>>();
const CACHE_TTL = 60_000;

async function fetchJson<T>(path: string): Promise<T> {
  // Browser fetch does not implement Next's server-side revalidation cache.
  const browser = typeof window !== "undefined";
  const cached = browser ? responseCache.get(path) : undefined;
  if (cached && cached.expires > Date.now()) return cached.value as T;
  const pending = browser ? pendingRequests.get(path) : undefined;
  if (pending) return pending as Promise<T>;

  const request = (async () => {
    const res = await fetch(`${API_BASE_URL}${path}`, { next: { revalidate: 60 } });
    if (!res.ok) throw new Error(`Error ${res.status} consultando ${path}`);
    const value = await res.json() as T;
    if (browser) {
      for (const [key, entry] of responseCache) {
        if (entry.expires <= Date.now()) responseCache.delete(key);
      }
      if (responseCache.size >= 100) responseCache.delete(responseCache.keys().next().value!);
      responseCache.set(path, { expires: Date.now() + CACHE_TTL, value });
    }
    return value;
  })();

export interface OpportunityDetail {
  first_detected_price?: number | null;
  current_price?: number | null;
  return_since_first_detected_pct?: number | null;
}
  if (browser) pendingRequests.set(path, request);
  try {
    return await request;
  } finally {
    if (browser) pendingRequests.delete(path);
  }
}

export async function getOpportunities(filters: OpportunityFilters = {}): Promise<Opportunity[]> {
  if (DEMO_MODE) {
    const { DEMO_OPPORTUNITIES } = await import("./demo-data");
    let result = [...DEMO_OPPORTUNITIES];
    if (filters.risk) result = result.filter((o) => o.risk_bucket === filters.risk);
    if (filters.sector) result = result.filter((o) => o.sector === filters.sector);
    if (filters.strategy === "early_stage2") {
      const early = result.filter((o) => o.weinstein.stage === 2 && o.weinstein.weeks_in_stage <= 6);
      return early.sort((a, b) => a.weinstein.weeks_in_stage - b.weinstein.weeks_in_stage);
    }
    return result.sort((a, b) => b.combined_score - a.combined_score);
  }

  const params = new URLSearchParams();
  if (filters.risk) params.set("risk", filters.risk);
  if (filters.sector) params.set("sector", filters.sector);
  if (filters.strategy) params.set("strategy", filters.strategy);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  const query = params.toString();
  return fetchJson<Opportunity[]>(`/opportunities${query ? `?${query}` : ""}`);
}

export async function getOpportunityDetail(symbol: string): Promise<OpportunityDetail> {
  if (DEMO_MODE) {
    const { getDemoDetail } = await import("./demo-data");
    const detail = getDemoDetail(symbol);
    if (!detail) throw new Error(`Ticker ${symbol} no existe en el set de demo`);
    return detail;
  }
  return fetchJson<OpportunityDetail>(`/opportunities/${symbol}`);
}

export type CatalystType = "earnings" | "insider_buy" | "macro_data";
export type CatalystClassification = "oro" | "plata" | "bronce";

export interface Catalyst {
  id: number;
  ticker: string | null;
  company_name: string | null;
  sector: string | null;
  catalyst_type: CatalystType;
  title: string;
  description: string | null;
  detected_date: string;
  extra: Record<string, unknown>;
  combined_score: number | null;
  classification: CatalystClassification | null;
  explanation: string | null;
}

export async function getCatalysts(days = 7): Promise<Catalyst[]> {
  if (DEMO_MODE) {
    const { DEMO_CATALYSTS } = await import("./demo-data");
    return DEMO_CATALYSTS;
  }
  return fetchJson<Catalyst[]>(`/catalysts?days=${days}`);
}

export type FearGreedRating = "extreme fear" | "fear" | "neutral" | "greed" | "extreme greed";

export interface FearGreedPoint {
  date: string;
  score: number;
  rating: string;
}

export interface FearGreed {
  score: number;
  rating: FearGreedRating;
  timestamp: string;
  previous_close: number;
  previous_1_week: number;
  previous_1_month: number;
  previous_1_year: number;
  history: FearGreedPoint[];
}

export async function getFearGreed(): Promise<FearGreed> {
  if (DEMO_MODE) {
    const { DEMO_FEAR_GREED } = await import("./demo-data");
    return DEMO_FEAR_GREED;
  }
  return fetchJson<FearGreed>("/catalysts/fear-greed");
}
