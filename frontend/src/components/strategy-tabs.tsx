"use client";

import { TrendingUp, Search, Award, DollarSign, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

export type ActiveStrategy = "todas" | "minervini" | "lynch" | "berkshire" | "dividendos";

const TABS: { key: ActiveStrategy; label: string; icon: React.ElementType }[] = [
  { key: "todas", label: "Todas", icon: Layers },
  { key: "minervini", label: "Minervini", icon: TrendingUp },
  { key: "lynch", label: "Lynch", icon: Search },
  { key: "berkshire", label: "Berkshire", icon: Award },
  { key: "dividendos", label: "Dividendos", icon: DollarSign },
];

interface StrategyTabsProps {
  active: ActiveStrategy;
  onChange: (strategy: ActiveStrategy) => void;
}

export function StrategyTabs({ active, onChange }: StrategyTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Filtrar por estrategia"
      className="flex flex-wrap gap-1.5"
    >
      {TABS.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          role="tab"
          aria-selected={active === key}
          onClick={() => onChange(key)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
            active === key
              ? "border-(--color-accent)/60 bg-(--color-accent)/15 text-(--color-accent)"
              : "border-border/60 bg-card text-muted-foreground hover:border-border hover:text-foreground",
          )}
        >
          <Icon className="size-3 shrink-0" aria-hidden />
          {label}
        </button>
      ))}
    </div>
  );
}
