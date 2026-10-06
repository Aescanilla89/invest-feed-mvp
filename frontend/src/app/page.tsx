import { CatalystsSection } from "@/components/catalysts-section";
import { FeedSection } from "@/components/feed-section";
import { Header } from "@/components/header";
import Link from "next/link";

export default function Home() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <div className="flex flex-col gap-12">
          <section className="flex flex-col gap-4 rounded-2xl border border-(--color-accent)/30 bg-(--color-accent)/8 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-7" aria-labelledby="founder-offer-title">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-(--color-accent)">Acceso fundador</p>
              <h2 id="founder-offer-title" className="mt-2 font-heading text-2xl font-semibold tracking-tight">
                Sigue el producto desde dentro por 149 € al año.
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Feed completo, criterios explicados, catalizadores e histórico de cartera modelo.
              </p>
            </div>
            <Link href="/pricing" className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg bg-(--color-accent) px-4 text-sm font-semibold text-(--color-accent-foreground) transition-opacity hover:opacity-90">
              Ver acceso Pro
            </Link>
          </section>
          <FeedSection />
          <CatalystsSection />
        </div>
      </main>
    </>
  );
}
