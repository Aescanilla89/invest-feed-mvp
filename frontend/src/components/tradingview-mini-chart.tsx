"use client";

import { useEffect, useRef, useId } from "react";

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
  const instanceId = useId().replace(/[^a-zA-Z0-9]/g, "");
  const tvSymbol = getTVSymbol(symbol);
  // ID por instancia: un ticker puede aparecer en varias secciones.
  const containerId = `tv-mini-${instanceId}`;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const mount = () => {
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
        // Verde bosque del tema (--primary en dark mode, oklch(68% 0.13 152) ≈ #5fb583),
        // en vez del azul por defecto de TradingView que choca con la paleta.
        trendLineColor: "rgba(95, 181, 131, 1)",
        underLineColor: "rgba(95, 181, 131, 0.07)",
        underLineBottomColor: "rgba(95, 181, 131, 0)",
        isTransparent: true,
        autosize: false,
        largeChartUrl: `https://www.tradingview.com/chart/?symbol=${tvSymbol}`,
      });
      el.appendChild(script);
    };

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        mount();
      }
    }, { rootMargin: "200px" });
    observer.observe(el);

    return () => {
      observer.disconnect();
      el.innerHTML = "";
    };
  }, [tvSymbol, containerId]);

  return <div ref={ref} className="tradingview-widget-container h-[180px] w-full" />;
}
