"use client";

import { useEffect, useState } from "react";
import { Activity, CircleHelp, RefreshCw, Waves } from "lucide-react";
import { getMarketDesk, type MarketDesk as MarketDeskData, type MarketIndicator } from "@/lib/api";

const regimeNames: Record<string, string> = {
  STRESS: "Estrés",
  "RISK-OFF": "Aversión al riesgo",
  NEUTRAL: "Neutral",
  "RISK-ON": "Favorable al riesgo",
  "STRONG RISK-ON": "Muy favorable al riesgo",
  "PARTIAL DATA": "Datos incompletos",
};

const indicatorNames: Record<string, string> = {
  WALCL: "Activos de la Fed",
  WRESBAL: "Reservas bancarias",
  WTREGEN: "Cuenta del Tesoro (TGA)",
  RRPONTSYD: "Repo inverso (ON RRP)",
  SOFR_EFFR: "Tensión de financiación",
};

function dateLabel(value: string | null) {
  return value
    ? new Date(`${value}T12:00:00Z`).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
    : "Sin dato";
}

function scoreColor(score: number | null) {
  if (score === null) return "text-slate-400";
  if (score >= 60) return "text-emerald-300";
  if (score < 40) return "text-rose-300";
  return "text-amber-200";
}

function scoreText(score: number | null) {
  if (score === null) return "Sin lectura";
  if (score >= 65) return "Favorable";
  if (score <= 40) return "Desfavorable";
  return "Mixta";
}

function spanishSignal(signal: string) {
  const labels: Record<string, string> = {
    supportive: "Aporta liquidez",
    improving: "Mejora",
    stable: "Estable",
    deteriorating: "Se deteriora",
    contained: "Contenido",
    elevated: "Elevado",
    watch: "En observación",
    mixed: "Mixto",
    "latest observation": "Última observación",
    context: "Contexto",
    unavailable: "No disponible",
    stale: "Desactualizado",
    missing: "Sin dato",
    fresh: "Vigente",
    old: "Antiguo",
    unknown: "Desconocido",
    weak: "Débil",
  };
  return labels[signal] ?? signal;
}

function spanishFrequency(value: string) {
  const labels: Record<string, string> = { daily: "diaria", weekly: "semanal", monthly: "mensual", quarterly: "trimestral", mixed: "mixta" };
  return labels[value] ?? "no especificada";
}

function formatIndicator(item: MarketIndicator) {
  if (item.value === null || !Number.isFinite(item.value)) return "—";
  if (["WALCL", "WRESBAL", "WTREGEN"].includes(item.key)) {
    return `${(item.value / 1_000_000).toLocaleString("es-ES", { maximumFractionDigits: 2 })} bill. $`;
  }
  if (item.key === "RRPONTSYD") return `${item.value.toLocaleString("es-ES", { maximumFractionDigits: 1 })} mil mill. $`;
  if (item.key === "SOFR_EFFR") return `${item.value.toLocaleString("es-ES", { maximumFractionDigits: 1 })} pb`;
  return `${item.value.toLocaleString("es-ES", { maximumFractionDigits: 2 })} %`;
}

function macroDirection(value: string, kind: "growth" | "inflation" | "labour") {
  if (value.includes("unavailable") || value.includes("INSUFFICIENT")) return "Sin datos suficientes";
  if (kind === "growth") {
    if (value === "cooling") return "Se enfría";
    if (value === "improving") return "Mejora";
    return "Estable";
  }
  if (kind === "inflation") {
    if (value.startsWith("rising")) return value.includes("above") ? "Sube; sobre el 2 %" : "Sube";
    if (value.startsWith("cooling")) return value.includes("above") ? "Baja; sobre el 2 %" : "Baja";
    return value.startsWith("stable") ? (value.includes("above") ? "Estable; sobre el 2 %" : "Estable") : "Sin datos suficientes";
  }
  if (value === "softening") return "Pierde fuerza";
  if (value === "stable") return "Estable";
  return "Sin datos suficientes";
}

function generatedBrief(data: MarketDeskData) {
  const regime = regimeNames[data.market_regime.label] ?? "Lectura parcial";
  const liquidityScore = data.liquidity.score;
  const liquidityText = liquidityScore === null
    ? "No hay datos suficientes para valorar la liquidez."
    : liquidityScore >= 60
      ? "La liquidez ofrece apoyo al mercado."
      : liquidityScore < 40
        ? "La liquidez muestra señales de drenaje."
        : "La liquidez presenta señales mixtas.";
  const stressText = data.stress.score === null
    ? "El estrés financiero no se puede valorar con los datos disponibles."
    : data.stress.score >= 60
      ? "El estrés financiero permanece contenido."
      : data.stress.score < 40
        ? "El estrés financiero está elevado y conviene vigilarlo."
        : "El estrés financiero ofrece una señal intermedia.";
  const growth = macroDirection(data.macro.growth, "growth").toLowerCase();
  const inflation = macroDirection(data.macro.inflation, "inflation").toLowerCase();
  const macroText = data.macro.regime === "INSUFFICIENT DATA"
    ? "La lectura macroeconómica aún es incompleta."
    : `El crecimiento ${growth} y la inflación ${inflation}.`;
  const coverageText = data.coverage.available < data.coverage.expected
    ? `Lectura parcial: ${data.coverage.available} de ${data.coverage.expected} señales disponibles; la confianza se reduce por los datos ausentes.`
    : `Régimen ${regime.toLowerCase()}: ${Math.round(data.market_regime.score ?? 0)} puntos. ${liquidityText} ${stressText} ${macroText}`;
  if (data.coverage.available < data.coverage.expected) {
    return `Régimen ${regime.toLowerCase()}${data.market_regime.score === null ? "" : `: ${Math.round(data.market_regime.score)} puntos`}. ${liquidityText} ${stressText} ${macroText} ${coverageText}`;
  }
  return coverageText;
}

function Why({ item }: { item: MarketIndicator }) {
  return (
    <details className="group">
      <summary aria-label={`Ver explicación de ${indicatorNames[item.key] ?? item.label}`} className="flex size-7 cursor-pointer list-none items-center justify-center rounded-full text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-200">
        <CircleHelp className="size-4" />
      </summary>
      <div className="absolute right-3 z-10 mt-1 w-72 rounded-xl border border-white/10 bg-[#172231] p-3 text-xs leading-relaxed text-slate-300 shadow-xl sm:right-6">
        <p>{item.value === null ? "No hay una observación válida y vigente; este indicador no se incluye en la puntuación." : `El valor observado es ${formatIndicator(item)} y su lectura es «${spanishSignal(item.signal).toLowerCase()}». Contribuye al análisis del panel; no es una previsión.`}</p>
        <p className="mt-2 text-slate-400">Fecha: {dateLabel(item.as_of)} · Frecuencia: {spanishFrequency(item.frequency)} · Estado: {spanishSignal(item.freshness)}</p>
        <p className="mt-2">Fuente: {item.source_url ? <a className="text-cyan-200 underline" href={item.source_url} target="_blank" rel="noreferrer">{item.source}</a> : item.source}. {item.score === null ? "Excluido de la puntuación." : `Aporta ${item.score}/100 al indicador.`}</p>
      </div>
    </details>
  );
}

function Kpi({ label, value, detail, score }: { label: string; value: string; detail: string; score: number | null }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.025] p-3.5 sm:p-4">
      <div className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-500">{label}</div>
      <div className={`mt-2 truncate text-sm font-semibold sm:text-base ${scoreColor(score)}`}>{value}</div>
      <div className="mt-1 text-[11px] text-slate-500">{detail}</div>
    </div>
  );
}

function LiquidityMetric({ item }: { item: MarketIndicator }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 border-b border-white/[0.06] py-2.5 last:border-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-xs text-slate-300">{indicatorNames[item.key] ?? item.label}</span>
        <Why item={item} />
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-xs tabular-nums text-slate-100">{formatIndicator(item)}</div>
        <div className="mt-0.5 text-[10px] text-slate-500">{dateLabel(item.as_of)} · {spanishSignal(item.signal)}</div>
      </div>
    </div>
  );
}

export function MarketDesk() {
  const [data, setData] = useState<MarketDeskData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    getMarketDesk().then((value) => { if (active) setData(value); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, []);

  const liquidityKeys = ["WALCL", "WRESBAL", "WTREGEN", "RRPONTSYD", "SOFR_EFFR"];
  const liquidityMetrics = data?.liquidity.indicators.filter((item) => liquidityKeys.includes(item.key)) ?? [];
  const inflation = data ? macroDirection(data.macro.inflation, "inflation") : "Cargando…";
  const growth = data ? macroDirection(data.macro.growth, "growth") : "Cargando…";

  return (
    <section className="overflow-hidden rounded-[24px] border border-white/[0.1] bg-[#0b111a] text-slate-100 shadow-[0_24px_70px_-45px_rgba(3,10,20,.9)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-4 sm:px-7">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[.22em] text-cyan-300">Tradefinder · Mesa de mercado</p>
          <p className="mt-1 text-xs text-slate-500">Lectura rápida del mercado estadounidense</p>
        </div>
        <div className="text-[10px] text-slate-500">{data ? `Actualizado ${new Date(data.updated_at).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC` : "Conectando con las fuentes"}</div>
      </div>

      {error ? (
        <div className="m-5 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-4 text-sm text-amber-100">La lectura de mercado no está disponible ahora. El resto de Tradefinder sigue operativo.</div>
      ) : (
        <div className="space-y-5 p-4 sm:space-y-6 sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 sm:p-5">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[.2em] text-slate-500">Régimen actual</div>
              <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className={`font-mono text-5xl font-medium leading-none tracking-[-.06em] tabular-nums sm:text-6xl ${scoreColor(data?.market_regime.score ?? null)}`}>{data?.market_regime.score === null || data?.market_regime.score === undefined ? "—" : Math.round(data.market_regime.score)}<span className="ml-1 text-xl text-slate-600">/100</span></span>
                <span className="text-base font-semibold text-white sm:text-lg">{data ? regimeNames[data.market_regime.label] ?? "Lectura parcial" : "Calculando lectura"}</span>
              </div>
            </div>
            <div className="text-xs text-slate-500">Confianza {data?.confidence ?? 0} % · {data?.coverage.available ?? 0}/{data?.coverage.expected ?? 0} señales</div>
          </div>

          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <Kpi label="Liquidez" value={data ? scoreText(data.liquidity.score) : "Cargando…"} detail={data?.liquidity.score === null ? "Datos insuficientes" : `${data?.liquidity.score === null ? "—" : Math.round(data?.liquidity.score ?? 0)} / 100`} score={data?.liquidity.score ?? null} />
            <Kpi label="Estrés financiero" value={data ? scoreText(data.stress.score) : "Cargando…"} detail={data?.stress.score === null ? "Datos insuficientes" : `${data?.stress.score === null ? "—" : Math.round(data?.stress.score ?? 0)} / 100`} score={data?.stress.score ?? null} />
            <Kpi label="Crecimiento" value={growth} detail="PIB y producción" score={null} />
            <Kpi label="Inflación" value={inflation} detail="IPC y PCE · referencia Fed 2 %" score={null} />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.1fr_.9fr]">
            <section className="rounded-2xl border border-cyan-300/[0.12] bg-cyan-300/[0.035] p-4 sm:p-5">
              <h2 className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.18em] text-cyan-100"><Activity className="size-3.5"/> Lectura de hoy</h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-200">{data ? generatedBrief(data) : <><RefreshCw className="mr-2 inline size-4 animate-spin"/>Esperando datos oficiales para preparar la lectura.</>}</p>
              <p className="mt-3 text-[10px] text-slate-600">Describe las condiciones observadas; no es una previsión de rentabilidad.</p>
            </section>

            <section className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 sm:p-5">
              <h2 className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.18em] text-slate-300"><Waves className="size-3.5 text-cyan-300"/> Liquidez en EE.UU.</h2>
              {liquidityMetrics.length ? <div className="mt-2">{liquidityMetrics.map((item) => <LiquidityMetric key={item.key} item={item}/>)}</div> : <p className="mt-3 text-xs text-slate-500">{data ? "No hay indicadores de liquidez vigentes." : "Cargando indicadores…"}</p>}
            </section>
          </div>

          <details className="border-t border-white/[0.07] pt-3 text-xs text-slate-500">
            <summary className="cursor-pointer font-medium text-slate-400 hover:text-slate-200">Fuentes y cómo se calcula</summary>
            <div className="mt-3 space-y-2 leading-relaxed">
              <p>El régimen combina liquidez (30 %), estrés financiero y crédito (30 %), macroeconomía (20 %) e indicadores de mercado (20 %). Si faltan datos, los pesos disponibles se reajustan y baja la confianza.</p>
              <p>La liquidez se valora con balance de la Fed, reservas bancarias, cuenta del Tesoro, repo inverso y diferencial SOFR–EFFR. El net liquidity es un proxy de mercado, no una identidad contable.</p>
              <p>Fuentes observadas: {data?.sources.join(" · ") || "FRED y Alpaca, cuando están configuradas"}. Cada indicador muestra su fecha y fuente al abrir el icono de ayuda.</p>
              <a href="/docs/MARKET_DESK.md" className="inline-block text-cyan-200 underline decoration-white/20 underline-offset-2">Ver metodología completa</a>
            </div>
          </details>
        </div>
      )}
    </section>
  );
}
