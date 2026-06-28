"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import type { PriceBar } from "@/lib/api";

interface WeinsteinChartProps {
  bars: PriceBar[];
  weeksInStage: number;
  isTransition: boolean;
}

function computeMA30(bars: PriceBar[]): { time: string; value: number }[] {
  const result: { time: string; value: number }[] = [];
  for (let i = 29; i < bars.length; i++) {
    const slice = bars.slice(i - 29, i + 1);
    const avg = slice.reduce((s, b) => s + b.close, 0) / 30;
    result.push({ time: bars[i].date, value: avg });
  }
  return result;
}

export function WeinsteinChart({ bars, weeksInStage, isTransition }: WeinsteinChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length < 2) return;
    const container = containerRef.current;

    const isDark = document.documentElement.classList.contains("dark");
    const textColor = isDark ? "rgba(200,200,200,0.65)" : "rgba(0,0,0,0.5)";
    const gridColor = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)";
    const bgColor = isDark ? "#0a0a0a" : "#ffffff";

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor,
        fontFamily: "inherit",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: gridColor, style: LineStyle.Dotted },
        horzLines: { color: gridColor, style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.2)", labelBackgroundColor: isDark ? "#333" : "#eee" },
        horzLine: { color: isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.2)", labelBackgroundColor: isDark ? "#333" : "#eee" },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.05, bottom: 0.28 },
      },
      timeScale: {
        borderVisible: false,
        barSpacing: 6,
      },
      width: container.clientWidth,
      height: 420,
    });

    // Velas
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    candleSeries.setData(
      bars.map((b) => ({ time: b.date, open: b.open, high: b.high, low: b.low, close: b.close }))
    );

    // MA30 Weinstein (naranja/ámbar)
    const ma30Series = chart.addLineSeries({
      color: "#f59e0b",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: false,
      title: "MA30",
    });
    ma30Series.setData(computeMA30(bars));

    // Volumen (histograma en panel inferior)
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });
    volumeSeries.setData(
      bars.map((b) => ({
        time: b.date,
        value: b.volume,
        color: b.close >= b.open ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)",
      }))
    );

    // Marcador Stage 1→2
    if (isTransition && weeksInStage >= 1 && weeksInStage <= bars.length) {
      const idx = bars.length - weeksInStage;
      const markerBar = bars[idx];
      if (markerBar) {
        candleSeries.setMarkers([
          {
            time: markerBar.date,
            position: "belowBar",
            color: "#22c55e",
            shape: "arrowUp",
            text: "Stage 1→2",
          },
        ]);
      }
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [bars, weeksInStage, isTransition]);

  if (bars.length < 2) {
    return (
      <p className="text-sm text-muted-foreground">
        Histórico de precio no disponible todavía.
      </p>
    );
  }

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />;
}
