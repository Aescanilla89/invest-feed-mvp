"use client";

import { useMemo } from "react";
import type { CanslimCriterion } from "@/lib/api";

const WIDTH = 600;
const PRICE_HEIGHT = 130;
const VOLUME_HEIGHT = 40;
const GAP = 8;
const LABEL_ROW_HEIGHT = 22;
const HEIGHT = PRICE_HEIGHT + GAP + VOLUME_HEIGHT + LABEL_ROW_HEIGHT;

const BASE_ZONE = { x0: 0, x1: 300 };
const BREAKOUT_ZONE = { x0: 300, x1: 370 };
const FOLLOWTHROUGH_ZONE = { x0: 370, x1: 600 };

const RESISTANCE_Y = 78;
const SUPPORT_Y = 100;
const BREAKOUT_TOP_Y = 25;

function buildPricePoints(): { x: number; y: number }[] {
  const points: { x: number; y: number }[] = [];
  for (let x = 0; x <= 300; x += 6) {
    points.push({ x, y: 89 + Math.sin(x / 18) * 10 });
  }
  for (let x = 300; x <= 370; x += 5) {
    const t = (x - 300) / 70;
    points.push({ x, y: 89 - t * (89 - BREAKOUT_TOP_Y) });
  }
  for (let x = 370; x <= 600; x += 8) {
    const t = (x - 370) / 230;
    points.push({ x, y: BREAKOUT_TOP_Y - t * 8 });
  }
  return points;
}

function buildVolumeBars(): { x: number; height: number; isBreakout: boolean }[] {
  const bars: { x: number; height: number; isBreakout: boolean }[] = [];
  for (let x = 4; x <= 296; x += 16) bars.push({ x, height: 6 + (x % 32 === 4 ? 4 : 0), isBreakout: false });
  bars.push({ x: 320, height: VOLUME_HEIGHT, isBreakout: true });
  bars.push({ x: 340, height: VOLUME_HEIGHT * 0.7, isBreakout: true });
  for (let x = 380; x <= 596; x += 18) bars.push({ x, height: 10 - ((x - 380) / 220) * 4, isBreakout: false });
  return bars;
}

export function CanslimPatternDiagram({
  newHighCriterion,
  relativeVolume,
}: {
  newHighCriterion: CanslimCriterion | undefined;
  relativeVolume: number;
}) {
  const pricePoints = useMemo(buildPricePoints, []);
  const volumeBars = useMemo(buildVolumeBars, []);
  const hasBrokenOut = newHighCriterion?.value === true;

  const pricePath = pricePoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const markerX = hasBrokenOut ? 500 : 150;
  const markerPoint = pricePoints.reduce((closest, p) => (Math.abs(p.x - markerX) < Math.abs(closest.x - markerX) ? p : closest));

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Diagrama del patrón base + ruptura de CAN SLIM">
        <line x1={BASE_ZONE.x0} x2={BREAKOUT_ZONE.x1} y1={RESISTANCE_Y} y2={RESISTANCE_Y} stroke="var(--muted-foreground)" strokeOpacity={0.4} strokeDasharray="4 4" />
        <line x1={BASE_ZONE.x0} x2={BASE_ZONE.x1} y1={SUPPORT_Y} y2={SUPPORT_Y} stroke="var(--muted-foreground)" strokeOpacity={0.25} strokeDasharray="4 4" />

        <path
          d={pricePath}
          fill="none"
          stroke={hasBrokenOut ? "var(--accent)" : "var(--stage-neutral)"}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        <circle cx={markerPoint.x} cy={markerPoint.y} r={6} fill="var(--background)" stroke="var(--accent)" strokeWidth={2.5} />

        <g transform={`translate(0, ${PRICE_HEIGHT + GAP})`}>
          {volumeBars.map((bar, i) => (
            <rect
              key={i}
              x={bar.x}
              y={VOLUME_HEIGHT - bar.height}
              width={10}
              height={bar.height}
              rx={1.5}
              fill={bar.isBreakout ? "var(--accent)" : "var(--stage-neutral)"}
              fillOpacity={bar.isBreakout ? 1 : 0.35}
            />
          ))}
        </g>

        <text x={130} y={HEIGHT - 4} textAnchor="middle" fontSize={11} fill={hasBrokenOut ? "var(--muted-foreground)" : "var(--accent)"} fontWeight={hasBrokenOut ? 400 : 600}>
          Base
        </text>
        <text x={335} y={HEIGHT - 4} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">
          Ruptura
        </text>
        <text x={530} y={HEIGHT - 4} textAnchor="middle" fontSize={11} fill={hasBrokenOut ? "var(--accent)" : "var(--muted-foreground)"} fontWeight={hasBrokenOut ? 600 : 400}>
          Continuación
        </text>
      </svg>

      <p className="mt-2 text-xs text-muted-foreground">
        {hasBrokenOut ? (
          <>
            <span className="font-medium text-foreground">Ya rompió la base</span> con volumen relativo de{" "}
            {relativeVolume.toFixed(2)}x sobre su media — la fase que CAN SLIM busca confirmar con el criterio N.
          </>
        ) : (
          <>
            <span className="font-medium text-foreground">Todavía en fase de base</span>, sin ruptura confirmada sobre
            máximos de 52 semanas con volumen (criterio N). Volumen relativo actual: {relativeVolume.toFixed(2)}x.
          </>
        )}{" "}
        Esquema idealizado del patrón, no una proyección de precio real.
      </p>
    </div>
  );
}
