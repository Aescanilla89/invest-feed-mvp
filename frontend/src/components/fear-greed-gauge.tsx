"use client";

import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import type { FearGreed, FearGreedRating } from "@/lib/api";
import { cn } from "@/lib/utils";

const RATING_LABEL: Record<FearGreedRating, string> = {
  "extreme fear": "Miedo extremo",
  fear: "Miedo",
  neutral: "Neutral",
  greed: "Codicia",
  "extreme greed": "Codicia extrema",
};

// Mismos tokens de riesgo que el resto de la app (bajo=verde, medio=ámbar,
// alto=rojo) -- aquí "alto riesgo" (rojo) es miedo y "bajo riesgo" (verde)
// es codicia, que es justo la escala de colores que usa CNN en su propio
// gauge, así que se reutilizan en vez de inventar una paleta nueva.
const RATING_COLOR: Record<FearGreedRating, string> = {
  "extreme fear": "text-(--color-risk-high)",
  fear: "text-(--color-risk-high)",
  neutral: "text-(--color-risk-medium)",
  greed: "text-(--color-risk-low)",
  "extreme greed": "text-(--color-risk-low)",
};

function normalizeRating(rating: string): FearGreedRating {
  return (rating in RATING_LABEL ? rating : "neutral") as FearGreedRating;
}

/** Ángulo de la aguja: -90deg (score 0, extremo izquierdo) a +90deg (score
 * 100, extremo derecho), pivotando en el centro del semicírculo. */
function needleAngle(score: number): number {
  const clamped = Math.max(0, Math.min(100, score));
  return (clamped / 100) * 180 - 90;
}

function DeltaRow({ label, value, current }: { label: string; value: number; current: number }) {
  const delta = current - value;
  const flat = Math.abs(delta) < 0.5;
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5 tabular-nums">
        <span className="text-foreground/70">{Math.round(value)}</span>
        {!flat && (
          <span className={delta > 0 ? "text-(--color-risk-low)" : "text-(--color-risk-high)"}>
            ({delta > 0 ? "+" : ""}
            {Math.round(delta)})
          </span>
        )}
      </span>
    </div>
  );
}

export function FearGreedGauge({ data }: { data: FearGreed }) {
  const rating = normalizeRating(data.rating);
  // La aguja arranca en 50 (neutral) y anima hasta el score real al montar
  // -- el pequeño delay es a propósito, para que la transición CSS se note
  // en vez de aparecer ya en su posición final.
  const [displayScore, setDisplayScore] = useState(50);
  useEffect(() => {
    const t = setTimeout(() => setDisplayScore(data.score), 150);
    return () => clearTimeout(t);
  }, [data.score]);

  const angle = needleAngle(displayScore);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5 sm:flex-row sm:items-center sm:gap-6">
      <div className="relative mx-auto w-full max-w-[240px] shrink-0 sm:mx-0">
        <svg viewBox="0 0 200 118" className="w-full overflow-visible">
          <defs>
            <linearGradient id="fgGaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="var(--risk-high)" />
              <stop offset="50%" stopColor="var(--risk-medium)" />
              <stop offset="100%" stopColor="var(--risk-low)" />
            </linearGradient>
          </defs>

          {/* Arco de fondo (track) */}
          <path
            d="M 16 100 A 84 84 0 0 1 184 100"
            fill="none"
            stroke="var(--muted)"
            strokeWidth="14"
            strokeLinecap="round"
          />
          {/* Arco de color -- miedo (rojo) a codicia (verde) */}
          <path
            d="M 16 100 A 84 84 0 0 1 184 100"
            fill="none"
            stroke="url(#fgGaugeGradient)"
            strokeWidth="14"
            strokeLinecap="round"
          />

          {/* Aguja */}
          <g style={{ transform: `rotate(${angle}deg)`, transformOrigin: "100px 100px", transition: "transform 1s cubic-bezier(0.22, 1, 0.36, 1)" }}>
            <line x1="100" y1="100" x2="100" y2="28" stroke="currentColor" strokeWidth="3" strokeLinecap="round" className="text-foreground" />
          </g>
          <circle cx="100" cy="100" r="7" fill="currentColor" className="text-foreground" />

          <text x="16" y="114" fontSize="8" fill="var(--muted-foreground)">
            Miedo
          </text>
          <text x="184" y="114" fontSize="8" fill="var(--muted-foreground)" textAnchor="end">
            Codicia
          </text>
        </svg>

        <div className="mt-1 flex flex-col items-center">
          <span className={cn("font-heading text-4xl font-bold leading-none tabular-nums", RATING_COLOR[rating])}>
            {Math.round(data.score)}
          </span>
          <span className={cn("mt-1 text-sm font-medium", RATING_COLOR[rating])}>{RATING_LABEL[rating]}</span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Gauge className="size-4 shrink-0" aria-hidden />
          <h3 className="font-heading text-sm font-semibold text-foreground">Fear &amp; Greed Index</h3>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Sentimiento del mercado de CNN Business (0-100), media de 7 indicadores: momentum de precio,
          amplitud de mercado, demanda de bonos basura vs. calidad, volatilidad y demanda de refugio.
        </p>
        <div className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
          <DeltaRow label="Ayer" value={data.previous_close} current={data.score} />
          <DeltaRow label="Hace 1 semana" value={data.previous_1_week} current={data.score} />
          <DeltaRow label="Hace 1 mes" value={data.previous_1_month} current={data.score} />
          <DeltaRow label="Hace 1 año" value={data.previous_1_year} current={data.score} />
        </div>
      </div>
    </div>
  );
}
