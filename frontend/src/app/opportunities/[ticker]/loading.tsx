export default function OpportunityDetailLoading() {
  return (
    <main
      className="mx-auto w-full max-w-4xl flex-1 px-6 py-8"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="h-5 w-36 animate-pulse rounded bg-muted" />
      <div className="mt-8 h-12 w-64 animate-pulse rounded bg-muted" />
      <div className="mt-3 h-5 w-48 animate-pulse rounded bg-muted" />
      <p className="mt-8 text-sm text-muted-foreground">Preparando el análisis de mercado…</p>
      <div className="mt-6 h-28 animate-pulse rounded-xl bg-muted/60" />
      <div className="mt-6 h-[420px] animate-pulse rounded-xl bg-muted/60" />
    </main>
  );
}
