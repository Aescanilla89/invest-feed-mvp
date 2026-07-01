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

function getTVSymbol(symbol: string): string {
  for (const [suffix, exchange] of Object.entries(SUFFIX_TO_EXCHANGE)) {
    if (symbol.endsWith(suffix)) {
      return `${exchange}:${symbol.slice(0, -suffix.length)}`;
    }
  }
  return symbol;
}

export function TradingViewMiniChart({ symbol }: { symbol: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    el.innerHTML = "";

    const inner = document.createElement("div");
    inner.className = "tradingview-widget-container__widget";
    el.appendChild(inner);

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol: getTVSymbol(symbol),
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
      largeChartUrl: "",
    });
    el.appendChild(script);

    return () => {
      el.innerHTML = "";
    };
  }, [symbol]);

  return <div ref={ref} className="tradingview-widget-container h-[180px] w-full" />;
}
