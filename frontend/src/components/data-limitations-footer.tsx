import { getDataLimitations } from "@/lib/api";
import { CANSLIM_LABELS } from "@/lib/canslim-labels";

export async function DataLimitationsFooter() {
  let limitations;
  try {
    limitations = await getDataLimitations();
  } catch {
    limitations = null;
  }

  return (
    <footer className="border-t border-border/60">
      <div className="mx-auto max-w-6xl px-6 py-10 text-sm">
        <h2 className="font-heading text-base font-semibold">Qué hay detrás de los números</h2>
        {limitations ? (
          <div className="mt-4 grid gap-8 sm:grid-cols-2">
            <ul className="space-y-2 text-muted-foreground">
              {limitations.source_notes.map((note, i) => (
                <li key={i} className="leading-relaxed">
                  {note}
                </li>
              ))}
            </ul>
            <ul className="space-y-1.5 text-muted-foreground">
              {limitations.canslim_criteria.map((c) => (
                <li key={c.criterion} className="leading-relaxed">
                  <span className="font-medium text-foreground">
                    {c.criterion} — {CANSLIM_LABELS[c.criterion]}:
                  </span>{" "}
                  {c.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-3 text-muted-foreground">
            No se pudo cargar el detalle de limitaciones de datos ahora mismo.
          </p>
        )}
        <p className="mt-8 text-xs text-muted-foreground/70">StageWise — proyecto educativo, sin fines de asesoramiento.</p>
      </div>
    </footer>
  );
}
