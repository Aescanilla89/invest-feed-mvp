"use client";

import { useId, useMemo, useState } from "react";

interface PricePoint {
  date: string;
  close: number;
  volume: number;
}

const WIDTH = 640;
const HEIGHT = 220;
const PADDING_X = 8;
const PADDING_TOP = 16;
const PADDING_BOTTOM = 24;

export function PriceChart({ points }: { points: PricePoint[] }) {
  const gradientId = useId();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const chart = useMemo(() => {
    if (points.length < 2) return null;
    const closes = points.map((p) => p.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;
    const plotWidth = WIDTH - PADDING_X * 2;
    const plotHeight = HEIGHT - PADDING_TOP - PADDING_BOTTOM;

    const coords = points.map((p, i) => {
      const x = PADDING_X + (i / (points.length - 1)) * plotWidth;
      const y = PADDING_TOP + plotHeight - ((p.close - min) / range) * plotHeight;
      return { x, y, ...p };
    });

    const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
    const areaPath = `${linePath} L${coords[coords.length - 1].x.toFixed(1)},${HEIGHT - PADDING_BOTTOM} L${coords[0].x.toFixed(1)},${HEIGHT - PADDING_BOTTOM} Z`;

    return { coords, min, max };
  }, [points]);

  if (!chart) {
    return <p className="text-sm text-muted-foreground">Histórico de precio no disponible ahora mismo.</p>;
  }

  const hovered = hoverIndex !== null ? chart.coords[hoverIndex] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label={`Evolución del precio de cierre semanal, de ${chart.min.toFixed(2)} a ${chart.max.toFixed(2)}`}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--stage-advance)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--stage-advance)" stopOpacity="0" />
          </linearGradient>
        </defs>

        <path
          d={`${chart.coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ")} L${chart.coords[chart.coords.length - 1].x.toFixed(1)},${HEIGHT - PADDING_BOTTOM} L${chart.coords[0].x.toFixed(1)},${HEIGHT - PADDING_BOTTOM} Z`}
          fill={`url(#${gradientId})`}
        />
        <path
          d={chart.coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ")}
          fill="none"
          stroke="var(--stage-advance)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {chart.coords.map((c, i) => (
          <rect
            key={c.date}
            x={c.x - WIDTH / chart.coords.length / 2}
            y={0}
            width={WIDTH / chart.coords.length}
            height={HEIGHT}
            fill="transparent"
            onMouseEnter={() => setHoverIndex(i)}
          />
        ))}

        {hovered && (
          <>
            <line x1={hovered.x} x2={hovered.x} y1={PADDING_TOP} y2={HEIGHT - PADDING_BOTTOM} stroke="var(--border)" strokeWidth={1} />
            <circle cx={hovered.x} cy={hovered.y} r={3.5} fill="var(--stage-advance)" />
          </>
        )}
      </svg>

      <div className="mt-1 flex justify-between text-xs text-muted-foreground tabular">
        <span>{points[0].date}</span>
        <span>{points[points.length - 1].date}</span>
      </div>

      {hovered && (
        <div className="pointer-events-none absolute top-0 rounded-md bg-popover px-2 py-1 text-xs shadow-md ring-1 ring-foreground/10" style={{ left: `${(hovered.x / WIDTH) * 100}%`, transform: "translateX(-50%)" }}>
          <p className="font-medium tabular">${hovered.close.toFixed(2)}</p>
          <p className="text-muted-foreground">{hovered.date}</p>
        </div>
      )}
    </div>
  );
}
