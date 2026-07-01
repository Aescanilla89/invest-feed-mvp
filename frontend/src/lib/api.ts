const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

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
  ticker: string;
  name: string | null;
  sector: string | null;
  combined_score: number;
  risk_bucket: RiskBucket;
  weinstein: Weinstein;
  canslim: Canslim;
  explanation: string | null;
  last_updated: string;
  signal_type?: SignalType;
  strategies: Record<StrategyName, StrategyResult>;
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

export interface DataLimitation {
  criterion: string;
  verifiable: boolean;
  reason: string;
}

export interface DataLimitations {
  source_notes: string[];
  canslim_criteria: DataLimitation[];
}

export interface OpportunityFilters {
  minScore?: number;
  risk?: RiskBucket;
  sector?: string;
  sort?: "score" | "stage";
  strategy?: StrategyName | "weinstein" | "canslim";
  limit?: number;
}

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error ${res.status} consultando ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function getOpportunities(filters: OpportunityFilters = {}): Promise<Opportunity[]> {
  if (DEMO_MODE) {
    const { DEMO_OPPORTUNITIES } = await import("./demo-data");
    let result = DEMO_OPPORTUNITIES.filter((o) => o.combined_score >= (filters.minScore ?? 0));
    if (filters.risk) result = result.filter((o) => o.risk_bucket === filters.risk);
    if (filters.sector) result = result.filter((o) => o.sector === filters.sector);
    return [...result].sort((a, b) => b.combined_score - a.combined_score);
  }

  const params = new URLSearchParams();
  if (filters.minScore) params.set("min_score", String(filters.minScore));
  if (filters.risk) params.set("risk", filters.risk);
  if (filters.sector) params.set("sector", filters.sector);
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.strategy) params.set("strategy", filters.strategy);
  if (filters.limit) params.set("limit", String(filters.limit));
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

export async function getDataLimitations(): Promise<DataLimitations> {
  if (DEMO_MODE) {
    const { DEMO_LIMITATIONS } = await import("./demo-data");
    return DEMO_LIMITATIONS;
  }
  return fetchJson<DataLimitations>("/meta/data-limitations");
}
