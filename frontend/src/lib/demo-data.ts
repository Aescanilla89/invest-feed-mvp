/**
 * Datos fijos para el modo demo (NEXT_PUBLIC_DEMO_MODE=true), usado solo
 * en el deploy de preview de Vercel -- ese entorno no tiene acceso al
 * backend real (FastAPI + SQLite no corren en serverless). Los números y
 * criterios son una captura real de una corrida del screener; las
 * explicaciones de GOOGL/JPM/KO/XOM están escritas a mano siguiendo el
 * mismo estilo que genera Claude (NVDA y AAPL sí son explicaciones reales
 * generadas por la API en una corrida anterior). En desarrollo local y en
 * producción real, este fichero no se usa -- lib/api.ts solo lo importa
 * si NEXT_PUBLIC_DEMO_MODE está activo.
 */
import type { DataLimitations, Opportunity, OpportunityDetail } from "./api";

export const DEMO_OPPORTUNITIES: Opportunity[] = [
  {
    ticker: "XOM",
    name: "Exxon Mobil Corporation",
    sector: "Energy",
    combined_score: 75,
    risk_bucket: "medio",
    weinstein: { stage: 2, is_transition: true, weeks_in_stage: 35, ma_slope_pct: 0.0346, relative_volume: 0.573, rsi: 62.4 },
    canslim: {
      score: "3/6 verificables",
      criteria: {
        C: { value: false, detail: "Crecimiento EPS trimestral YoY: -43.2% (umbral 25%)" },
        A: { value: false, detail: "Crecimiento EPS anual: -14.5% (umbral 25%)" },
        N: { value: false, detail: "Cierre 136.90 vs máx 52sem 175.22 (78.1% del máximo); volumen relativo 0.57x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: true, detail: "Shares outstanding variación 4 trimestres: -3.8%" },
        L: { value: true, detail: "Retorno 52sem: ticker 25.9% vs benchmark 18.6% (diff +7.3%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation:
      "Exxon Mobil lleva 35 semanas en Stage 2 de Weinstein, con la media de 30 semanas inclinada +3.5% y una transición 1→2 detectada en la ventana reciente, lo que sostiene la tendencia técnica a pesar de fundamentales débiles: el EPS trimestral cae -43.2% y el anual -14.5%, muy lejos del umbral CAN SLIM del 25%. La fuerza relativa frente al mercado (+7.3%) y la reducción de acciones en circulación (-3.8%, recompras) son lo que compensa esos fundamentales flojos en el score combinado.",
    last_updated: "2026-06-25",
  },
  {
    ticker: "NVDA",
    name: "NVIDIA Corporation",
    sector: "Technology",
    combined_score: 68,
    risk_bucket: "medio",
    weinstein: { stage: 2, is_transition: false, weeks_in_stage: 11, ma_slope_pct: 0.0168, relative_volume: 0.5698, rsi: 58.1 },
    canslim: {
      score: "4/6 verificables",
      criteria: {
        C: { value: true, detail: "Crecimiento EPS trimestral YoY: 214.5% (umbral 25%)" },
        A: { value: true, detail: "Crecimiento EPS anual: 66.7% (umbral 25%)" },
        N: { value: false, detail: "Cierre 199.00 vs máx 52sem 236.26 (84.2% del máximo); volumen relativo 0.57x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: false, detail: "Shares outstanding variación 4 trimestres: -0.8%" },
        L: { value: true, detail: "Retorno 52sem: ticker 25.1% vs benchmark 18.6% (diff +6.5%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation:
      "NVIDIA presenta fundamentales sólidos con un crecimiento de EPS trimestral del 214,5%, pero la señal técnica es débil en este momento: el volumen relativo de solo 0,57x indica que la acción no está atrayendo demanda institucional suficiente para confirmar continuación del Stage 2 con convicción. Cotizando al 84,2% de su máximo de 52 semanas sin catalizador de volumen, el criterio N de CAN SLIM no se cumple, lo que sugiere que la fortaleza fundamental aún no se ha traducido en presión compradora técnica verificable.",
    last_updated: "2026-06-25",
  },
  {
    ticker: "GOOGL",
    name: "Alphabet Inc.",
    sector: "Communication Services",
    combined_score: 68,
    risk_bucket: "medio",
    weinstein: { stage: 2, is_transition: false, weeks_in_stage: 44, ma_slope_pct: 0.0382, relative_volume: 0.9159, rsi: 67.3 },
    canslim: {
      score: "4/6 verificables",
      criteria: {
        C: { value: true, detail: "Crecimiento EPS trimestral YoY: 81.9% (umbral 25%)" },
        A: { value: true, detail: "Crecimiento EPS anual: 34.5% (umbral 25%)" },
        N: { value: false, detail: "Cierre 345.29 vs máx 52sem 408.37 (84.6% del máximo); volumen relativo 0.92x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: false, detail: "Shares outstanding variación 4 trimestres: +0.1%" },
        L: { value: true, detail: "Retorno 52sem: ticker 92.9% vs benchmark 18.6% (diff +74.3%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation:
      "Alphabet combina fundamentales fuertes (EPS trimestral +81.9%, anual +34.5%, ambos muy por encima del umbral CAN SLIM del 25%) con una fuerza relativa extraordinaria: +74.3 puntos sobre el S&P 500 en 52 semanas. Lleva 44 semanas en Stage 2 con la media de 30 semanas todavía subiendo (+3.8%), aunque el volumen relativo de 0.92x no confirma una ruptura reciente sobre máximos de 52 semanas (criterio N), señal de que el mercado aún no ha acelerado la entrada de dinero sobre el precio.",
    last_updated: "2026-06-25",
  },
  {
    ticker: "AAPL",
    name: "Apple Inc.",
    sector: "Technology",
    combined_score: 60,
    risk_bucket: "bajo",
    weinstein: { stage: 2, is_transition: false, weeks_in_stage: 39, ma_slope_pct: 0.0178, relative_volume: 0.6549, rsi: 55.8 },
    canslim: {
      score: "3/6 verificables",
      criteria: {
        C: { value: false, detail: "Crecimiento EPS trimestral YoY: 21.8% (umbral 25%)" },
        A: { value: false, detail: "Crecimiento EPS anual: 22.7% (umbral 25%)" },
        N: { value: false, detail: "Cierre 293.08 vs máx 52sem 317.40 (92.3% del máximo); volumen relativo 0.65x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: true, detail: "Shares outstanding variación 4 trimestres: -1.7%" },
        L: { value: true, detail: "Retorno 52sem: ticker 37.8% vs benchmark 18.6% (diff +19.2%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation:
      "AAPL lleva 39 semanas en Stage 2 de Weinstein con la media de 30 semanas inclinada +1.8%, lo que confirma tendencia alcista sostenida, pero el volumen relativo de 0.65x (muy por debajo del umbral 1.5x) indica falta de convicción institucional en el movimiento. Los criterios CAN SLIM son débiles: el crecimiento de EPS trimestral (21.8%) y anual (22.7%) quedan por debajo del umbral del 25%, y el precio está un 7.7% alejado de máximos de 52 semanas sin catalizador de volumen, por lo que los fundamentos de aceleración de beneficios que busca CAN SLIM no se verifican en este momento.",
    last_updated: "2026-06-25",
  },
  {
    ticker: "JPM",
    name: "JP Morgan Chase & Co.",
    sector: "Financial Services",
    combined_score: 52,
    risk_bucket: "bajo",
    weinstein: { stage: 2, is_transition: false, weeks_in_stage: 2, ma_slope_pct: 0.0072, relative_volume: 0.6398, rsi: 52.1 },
    canslim: {
      score: "2/6 verificables",
      criteria: {
        C: { value: false, detail: "Crecimiento EPS trimestral YoY: 17.2% (umbral 25%)" },
        A: { value: false, detail: "Crecimiento EPS anual: 1.4% (umbral 25%)" },
        N: { value: false, detail: "Cierre 333.45 vs máx 52sem 338.09 (98.6% del máximo); volumen relativo 0.64x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: true, detail: "Shares outstanding variación 4 trimestres: -3.6%" },
        L: { value: false, detail: "Retorno 52sem: ticker 14.3% vs benchmark 18.6% (diff -4.3%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation:
      "JP Morgan lleva solo 2 semanas en Stage 2 de Weinstein, con la media de 30 semanas apenas inclinada (+0.7%) y cotizando al 98.6% de su máximo de 52 semanas, aunque sin el volumen (0.64x) que CAN SLIM exige para confirmar una ruptura real. Los fundamentales son mixtos: el crecimiento de EPS trimestral (17.2%) y anual (1.4%) quedan por debajo del umbral del 25%, y la fuerza relativa frente al mercado es negativa (-4.3%), por lo que la señal técnica todavía no está respaldada por aceleración de beneficios.",
    last_updated: "2026-06-25",
  },
  {
    ticker: "KO",
    name: "Coca-Cola Company (The)",
    sector: "Consumer Defensive",
    combined_score: 43,
    risk_bucket: "bajo",
    weinstein: { stage: 2, is_transition: false, weeks_in_stage: 22, ma_slope_pct: 0.0226, relative_volume: 0.7761, rsi: 59.4 },
    canslim: {
      score: "1/6 verificables",
      criteria: {
        C: { value: false, detail: "Crecimiento EPS trimestral YoY: 18.2% (umbral 25%)" },
        A: { value: false, detail: "Crecimiento EPS anual: 23.6% (umbral 25%)" },
        N: { value: false, detail: "Cierre 80.60 vs máx 52sem 83.50 (96.5% del máximo); volumen relativo 0.78x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: false, detail: "Shares outstanding variación 4 trimestres: -0.0%" },
        L: { value: false, detail: "Retorno 52sem: ticker 16.2% vs benchmark 18.6% (diff -2.4%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation:
      "Coca-Cola lleva 22 semanas en Stage 2 con la media de 30 semanas subiendo de forma moderada (+2.3%), pero ninguno de los criterios fundamentales de CAN SLIM se cumple con holgura: el crecimiento de EPS trimestral (18.2%) y anual (23.6%) se quedan justo por debajo del umbral del 25%, y la fuerza relativa frente al mercado es ligeramente negativa (-2.4%). Es una tendencia técnica estable pero sin el catalizador de aceleración de beneficios que el método busca confirmar.",
    last_updated: "2026-06-25",
  },
  {
    ticker: "TSLA",
    name: "Tesla, Inc.",
    sector: "Consumer Cyclical",
    combined_score: 17,
    risk_bucket: "alto",
    weinstein: { stage: 4, is_transition: false, weeks_in_stage: 1, ma_slope_pct: -0.0082, relative_volume: 0.5591, rsi: 38.2 },
    canslim: {
      score: "2/6 verificables",
      criteria: {
        C: { value: false, detail: "Crecimiento EPS trimestral YoY: 8.3% (umbral 25%)" },
        A: { value: false, detail: "Crecimiento EPS anual: -47.1% (umbral 25%)" },
        N: { value: false, detail: "Cierre 375.53 vs máx 52sem 498.83 (75.3% del máximo); volumen relativo 0.56x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: false, detail: "Shares outstanding variación 4 trimestres: +16.4%" },
        L: { value: true, detail: "Retorno 52sem: ticker 19.1% vs benchmark 18.6% (diff +0.5%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation: null,
    last_updated: "2026-06-25",
  },
  {
    ticker: "MSFT",
    name: "Microsoft Corporation",
    sector: "Technology",
    combined_score: 8,
    risk_bucket: "medio",
    weinstein: { stage: 4, is_transition: false, weeks_in_stage: 22, ma_slope_pct: -0.0361, relative_volume: 0.7685, rsi: 31.6 },
    canslim: {
      score: "1/6 verificables",
      criteria: {
        C: { value: false, detail: "Crecimiento EPS trimestral YoY: 23.4% (umbral 25%)" },
        A: { value: false, detail: "Crecimiento EPS anual: 15.6% (umbral 25%)" },
        N: { value: false, detail: "Cierre 365.46 vs máx 52sem 551.05 (66.3% del máximo); volumen relativo 0.77x (umbral 1.5x). No evalúa 'nuevo producto/gestión' (no verificable con datos)." },
        S: { value: false, detail: "Shares outstanding variación 4 trimestres: -0.1%" },
        L: { value: false, detail: "Retorno 52sem: ticker -26.2% vs benchmark 18.6% (diff -44.7%)" },
        I: { value: null, detail: "No verificable en este MVP: requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC), no disponible como endpoint por ticker. Planificado para fase 2." },
        M: { value: true, detail: "Stage de Weinstein del benchmark (mercado general): 2" },
      },
    },
    explanation: null,
    last_updated: "2026-06-25",
  },
];

export const DEMO_LIMITATIONS: DataLimitations = {
  source_notes: [
    "yfinance no es una API oficial (scraping de Yahoo Finance): sin SLA, puede romperse sin aviso.",
    "Rate limit de yfinance no documentado oficialmente; el job aplica pausas entre tickers.",
    "Cobertura de datos fundamentales de yfinance es inconsistente fuera de empresas large-cap.",
    "SEC EDGAR (data.sec.gov) es la fuente oficial usada para shares outstanding (criterio S); gratis y sin API key, pero los filings tienen delay de varias semanas tras cierre de trimestre.",
    "Ningún dato de este feed tiene fines de ejecución de órdenes ni asesoramiento financiero: es información educativa, con retraso (no apto para intradía).",
  ],
  canslim_criteria: [
    { criterion: "C", verifiable: true, reason: "Crecimiento EPS trimestral YoY vía yfinance" },
    { criterion: "A", verifiable: true, reason: "Crecimiento EPS anual vía yfinance" },
    { criterion: "N", verifiable: true, reason: "Solo la parte de máximo de 52 semanas con volumen. No evalúa 'nuevo producto/gestión'." },
    { criterion: "S", verifiable: true, reason: "Tendencia de shares outstanding vía SEC EDGAR (companyfacts), no vía yfinance." },
    { criterion: "L", verifiable: true, reason: "Fuerza relativa frente a SPY como benchmark" },
    { criterion: "I", verifiable: false, reason: "Requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC). No disponible como endpoint por ticker en este MVP. Planificado para fase 2." },
    { criterion: "M", verifiable: true, reason: "Stage de Weinstein calculado sobre SPY como proxy del mercado" },
  ],
};

function toPriceBars(rows: { date: string; close: number; volume: number }[]): import("./api").PriceBar[] {
  return rows.map((r, i) => {
    const prevClose = i > 0 ? rows[i - 1].close : r.close * 0.99;
    const high = Math.max(prevClose, r.close) * 1.008;
    const low = Math.min(prevClose, r.close) * 0.992;
    return { date: r.date, open: prevClose, high, low, close: r.close, volume: r.volume };
  });
}

const REAL_PRICE_HISTORY: Record<string, { date: string; close: number; volume: number }[]> = {
  NVDA: [
    { date: "2025-07-04", close: 159.13, volume: 722664100 }, { date: "2025-07-11", close: 164.70, volume: 823265800 },
    { date: "2025-07-18", close: 172.18, volume: 833732200 }, { date: "2025-07-25", close: 173.27, volume: 721624000 },
    { date: "2025-08-01", close: 173.49, volume: 894627600 }, { date: "2025-08-08", close: 182.46, volume: 717049600 },
    { date: "2025-08-15", close: 180.21, volume: 749836800 }, { date: "2025-08-22", close: 177.75, volume: 845210200 },
    { date: "2025-08-29", close: 173.95, volume: 1092265600 }, { date: "2025-09-05", close: 166.80, volume: 761701300 },
    { date: "2025-09-12", close: 177.59, volume: 824239800 }, { date: "2025-09-19", close: 176.44, volume: 928588600 },
    { date: "2025-09-26", close: 177.96, volume: 945921100 }, { date: "2025-10-03", close: 187.38, volume: 878292100 },
    { date: "2025-10-10", close: 182.93, volume: 879706600 }, { date: "2025-10-17", close: 182.99, volume: 926433200 },
    { date: "2025-10-24", close: 186.02, volume: 657694900 }, { date: "2025-10-31", close: 202.23, volume: 1118935100 },
    { date: "2025-11-07", close: 187.91, volume: 1028509000 }, { date: "2025-11-14", close: 189.93, volume: 924330700 },
    { date: "2025-11-21", close: 178.65, volume: 1324905200 }, { date: "2025-11-28", close: 176.77, volume: 882403400 },
    { date: "2025-12-05", close: 182.19, volume: 847237200 }, { date: "2025-12-12", close: 174.81, volume: 898294700 },
    { date: "2025-12-19", close: 180.77, volume: 1037161100 }, { date: "2025-12-26", close: 190.30, volume: 509206800 },
    { date: "2026-01-02", close: 188.62, volume: 486034400 }, { date: "2026-01-09", close: 184.63, volume: 817720000 },
    { date: "2026-01-16", close: 186.00, volume: 851839300 }, { date: "2026-01-23", close: 187.44, volume: 706111000 },
    { date: "2026-01-30", close: 190.90, volume: 768317800 }, { date: "2026-02-06", close: 185.18, volume: 1014486900 },
    { date: "2026-02-13", close: 182.59, volume: 829165400 }, { date: "2026-02-20", close: 189.59, volume: 632002800 },
    { date: "2026-02-27", close: 176.97, volume: 1269789900 }, { date: "2026-03-06", close: 177.60, volume: 952727500 },
    { date: "2026-03-13", close: 180.04, volume: 818363600 }, { date: "2026-03-20", close: 172.50, volume: 968780300 },
    { date: "2026-03-27", close: 167.32, volume: 875471100 }, { date: "2026-04-03", close: 177.18, volume: 723083500 },
    { date: "2026-04-10", close: 188.41, volume: 664719900 }, { date: "2026-04-17", close: 201.45, volume: 774630900 },
    { date: "2026-04-24", close: 208.03, volume: 662523900 }, { date: "2026-05-01", close: 198.22, volume: 845045800 },
    { date: "2026-05-08", close: 214.95, volume: 731866800 }, { date: "2026-05-15", close: 225.06, volume: 832028300 },
    { date: "2026-05-22", close: 215.08, volume: 844088200 }, { date: "2026-05-29", close: 210.89, volume: 788210400 },
    { date: "2026-06-05", close: 205.10, volume: 955798300 }, { date: "2026-06-12", close: 205.19, volume: 751726900 },
    { date: "2026-06-19", close: 210.69, volume: 645266300 }, { date: "2026-06-26", close: 199.00, volume: 426361900 },
  ],
  XOM: [
    { date: "2025-07-04", close: 108.73, volume: 57851700 }, { date: "2025-07-11", close: 111.86, volume: 70567000 },
    { date: "2025-07-18", close: 104.44, volume: 80856500 }, { date: "2025-07-25", close: 106.99, volume: 69180100 },
    { date: "2025-08-01", close: 106.25, volume: 78163600 }, { date: "2025-08-08", close: 103.50, volume: 83651600 },
    { date: "2025-08-15", close: 104.16, volume: 78594200 }, { date: "2025-08-22", close: 108.85, volume: 73894900 },
    { date: "2025-08-29", close: 111.79, volume: 71939100 }, { date: "2025-09-05", close: 106.84, volume: 59817900 },
    { date: "2025-09-12", close: 109.71, volume: 68817800 }, { date: "2025-09-19", close: 110.35, volume: 96765700 },
    { date: "2025-09-26", close: 114.66, volume: 89318200 }, { date: "2025-10-03", close: 110.78, volume: 79892200 },
    { date: "2025-10-10", close: 108.31, volume: 61070600 }, { date: "2025-10-17", close: 109.78, volume: 58888900 },
    { date: "2025-10-24", close: 112.87, volume: 56585200 }, { date: "2025-10-31", close: 111.86, volume: 69467500 },
    { date: "2025-11-07", close: 114.66, volume: 72952700 }, { date: "2025-11-14", close: 117.70, volume: 77272200 },
    { date: "2025-11-21", close: 115.52, volume: 77831200 }, { date: "2025-11-28", close: 114.38, volume: 51360900 },
    { date: "2025-12-05", close: 114.99, volume: 70288700 }, { date: "2025-12-12", close: 117.24, volume: 87781500 },
    { date: "2025-12-19", close: 115.14, volume: 111618000 }, { date: "2025-12-26", close: 117.52, volume: 38539700 },
    { date: "2026-01-02", close: 121.02, volume: 50668000 }, { date: "2026-01-09", close: 122.95, volume: 110164200 },
    { date: "2026-01-16", close: 128.16, volume: 98520900 }, { date: "2026-01-23", close: 133.17, volume: 69715500 },
    { date: "2026-01-30", close: 139.52, volume: 111628700 }, { date: "2026-02-06", close: 147.06, volume: 130387300 },
    { date: "2026-02-13", close: 147.45, volume: 111007600 }, { date: "2026-02-20", close: 146.29, volume: 85829900 },
    { date: "2026-02-27", close: 151.47, volume: 91391500 }, { date: "2026-03-06", close: 150.19, volume: 117562500 },
    { date: "2026-03-13", close: 155.07, volume: 108915800 }, { date: "2026-03-20", close: 158.59, volume: 144399700 },
    { date: "2026-03-27", close: 169.84, volume: 117308900 }, { date: "2026-04-03", close: 159.61, volume: 125125500 },
    { date: "2026-04-10", close: 151.48, volume: 119816400 }, { date: "2026-04-17", close: 145.45, volume: 96978700 },
    { date: "2026-04-24", close: 147.91, volume: 74315300 }, { date: "2026-05-01", close: 151.72, volume: 82127600 },
    { date: "2026-05-08", close: 143.60, volume: 89319600 }, { date: "2026-05-15", close: 157.92, volume: 86279300 },
    { date: "2026-05-22", close: 154.92, volume: 89300700 }, { date: "2026-05-29", close: 145.26, volume: 71271300 },
    { date: "2026-06-05", close: 149.92, volume: 69950900 }, { date: "2026-06-12", close: 147.01, volume: 81629800 },
    { date: "2026-06-19", close: 137.81, volume: 107283400 }, { date: "2026-06-26", close: 136.90, volume: 45675500 },
  ],
};

function syntheticPriceHistory(opportunity: Opportunity): import("./api").PriceBar[] {
  const endClose = 100;
  const trendUp = opportunity.weinstein.stage === 2;
  const raw: { date: string; close: number; volume: number }[] = [];
  const start = new Date("2025-07-04");
  let price = trendUp ? endClose * 0.78 : endClose * 1.35;
  for (let i = 0; i < 52; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i * 7);
    const drift = trendUp ? 0.012 : -0.012;
    const noise = Math.sin(i * 1.3 + opportunity.ticker.length) * 0.025;
    price = price * (1 + drift + noise);
    raw.push({ date: d.toISOString().slice(0, 10), close: Math.round(price * 100) / 100, volume: 50_000_000 + Math.abs(Math.sin(i)) * 40_000_000 });
  }
  return toPriceBars(raw);
}

export function getDemoDetail(ticker: string): OpportunityDetail | null {
  const opportunity = DEMO_OPPORTUNITIES.find((o) => o.ticker === ticker.toUpperCase());
  if (!opportunity) return null;
  const rawHistory = REAL_PRICE_HISTORY[opportunity.ticker];
  const priceHistory = rawHistory ? toPriceBars(rawHistory) : syntheticPriceHistory(opportunity);
  return { ...opportunity, price_history: priceHistory };
}
