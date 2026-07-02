import { SearchX, WifiOff } from "lucide-react";

interface EmptyStateProps {
  message: string;
  detail?: string;
  icon?: React.ElementType;
}

export function EmptyState({ message, detail, icon: Icon = SearchX }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border py-16 text-center">
      <Icon className="size-8 text-muted-foreground/50" aria-hidden />
      <div className="max-w-sm text-sm text-muted-foreground">
        <p>
          {message}
          <span className="ml-0.5 inline-block w-[1px] text-(--color-accent) motion-safe:animate-pulse" aria-hidden>
            |
          </span>
        </p>
        {detail && <p className="mt-1 text-xs text-muted-foreground/70">{detail}</p>}
      </div>
    </div>
  );
}

/** Estado de error de carga -- deliberadamente calmado (no rojo alarmante):
 * es una desconexión temporal con el backend, no un fallo crítico. */
export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
      <WifiOff className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <p>{message}</p>
    </div>
  );
}
