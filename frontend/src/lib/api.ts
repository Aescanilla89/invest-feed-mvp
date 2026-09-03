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
  first_detected_date?: string | null;
  signal_type?: SignalType;
  strategies: Partial<Record<StrategyName, StrategyResult>>;
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
}

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

async function fetchJson<T>(path: string): Promise<T> {
  // Los datos solo cambian una vez al día (cron de las 4am) -- cache: "no-store"
  // forzaba ida y vuelta al backend (Render free tier, compute limitado) en
  // CADA carga de página, para todos los visitantes. Con revalidate: 60,
  // Vercel sirve la respuesta cacheada durante ese minuto y solo un visitante
  // paga el coste de refrescarla, en vez de todos.
  const res = await fetch(`${API_BASE_URL}${path}`, { next: { revalidate: 60 } });
  if (!res.ok) {
    throw new Error(`Error ${res.status} consultando ${path}`);
  }
  return res.json() as Promise<T>;
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

export type PortfolioMethod = StrategyName | "early_stage2";
export type PortfolioStatus = "open" | "closed";

export interface PortfolioPosition {
  ticker: string;
  name: string | null;
  sector: string | null;
  method: PortfolioMethod;
  status: PortfolioStatus;
  explanation: string | null;
  signal_date: string | null;
  entry_date: string;
  entry_price: number;
  current_price: number;
  return_pct: number;
  spy_return_pct: number;
  exit_signal_date: string | null;
  exit_date: string | null;
  exit_reason: string | null;
}

export interface PortfolioStats {
  total_positions: number;
  open_positions: number;
  closed_positions: number;
  ytd_return_pct: number | null;
  ytd_spy_return_pct: number | null;
  best: PortfolioPosition | null;
  worst: PortfolioPosition | null;
}

export interface Portfolio {
  stats: PortfolioStats;
  positions: PortfolioPosition[];
}

export async function getPortfolio(): Promise<Portfolio> {
  if (DEMO_MODE) {
    const { DEMO_PORTFOLIO } = await import("./demo-data");
    return DEMO_PORTFOLIO;
  }
  return fetchJson<Portfolio>("/portfolio");
}
