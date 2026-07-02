"use client";

import { useEffect, useRef } from "react";

const SUFFIX_TO_EXCHANGE: Record<string, string> = {
  ".L": "LSE",
  ".DE": "XETRA",
  ".PA": "EURONEXT",
  ".MC": "BME",
  ".MI": "MIL",
  ".AS": "EURONEXT",
};

// Tickers que usan punto en TradingView pero guión en nuestro DB (formato Alpaca)
// e.g. BRK-B → BRK.B, BF-B → BF.B
function normalizeTicker(symbol: string): string {
  return symbol.replace(/-([A-Z])$/, ".$1");
}

function getTVSymbol(symbol: string): string {
  const normalized = normalizeTicker(symbol);
  for (const [suffix, exchange] of Object.entries(SUFFIX_TO_EXCHANGE)) {
    if (normalized.endsWith(suffix)) {
      return `${exchange}:${normalized.slice(0, -suffix.length)}`;
    }
  }
  // Para tickers US: sin prefijo de exchange — TradingView auto-detecta NYSE/NASDAQ/AMEX
  // correctamente. Añadir NASDAQ: rompe tickers NYSE como GS, MS, JPM, etc.
  return normalized;
}

export function TradingViewMiniChart({ symbol }: { symbol: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const tvSymbol = getTVSymbol(symbol);
  // ID único por símbolo — evita que TradingView reutilice el widget de otro ticker en la grid
  const containerId = `tv-mini-${symbol.replace(/[^a-zA-Z0-9]/g, "_")}`;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    el.innerHTML = "";
    el.id = containerId;

    const inner = document.createElement("div");
    inner.className = "tradingview-widget-container__widget";
    el.appendChild(inner);

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol: tvSymbol,
      width: "100%",
      height: 180,
      locale: "es",
      dateRange: "12M",
      colorTheme: "dark",
      trendLineColor: "rgba(41, 98, 255, 1)",
      underLineColor: "rgba(41, 98, 255, 0.07)",
      underLineBottomColor: "rgba(41, 98, 255, 0)",
      isTransparent: true,
      autosize: false,
      largeChartUrl: `https://www.tradingview.com/chart/?symbol=${tvSymbol}`,
    });
    el.appendChild(script);

    return () => {
      el.innerHTML = "";
    };
  }, [tvSymbol, containerId]);

  return <div ref={ref} className="tradingview-widget-container h-[180px] w-full" />;
}
