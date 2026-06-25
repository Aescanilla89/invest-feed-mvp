import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function OpportunityCardSkeleton() {
  return (
    <Card className="flex flex-col gap-4 border-border/60 bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-9 w-12" />
      </div>
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-6 w-full" />
      <Skeleton className="h-16 w-full" />
    </Card>
  );
}
