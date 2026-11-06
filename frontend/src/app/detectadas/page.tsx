import { Header } from "@/components/header";
import { DetectedOpportunities } from "@/components/detected-opportunities";

export default function DetectedOpportunitiesPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <section>
          <h1 className="font-heading text-2xl font-semibold tracking-tight">Oportunidades detectadas</h1>
          <p className="mt-1 text-sm text-muted-foreground">Fecha de primera detección y variación del precio desde entonces.</p>
          <DetectedOpportunities />
        </section>
      </main>
    </>
  );
}
