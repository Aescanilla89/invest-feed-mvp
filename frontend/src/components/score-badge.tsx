import { cn } from "@/lib/utils";

export function ScoreBadge({ score }: { score: number }) {
  const tier = score >= 70 ? "high" : score >= 45 ? "mid" : "low";

  return (
    <div className="flex flex-col items-end">
      <span
        className={cn(
          "font-heading tabular text-3xl font-bold leading-none",
          tier === "high" && "text-(--color-stage-advance)",
          tier === "mid" && "text-foreground",
          tier === "low" && "text-muted-foreground",
        )}
      >
        {score}
      </span>
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">score /100</span>
    </div>
  );
}
