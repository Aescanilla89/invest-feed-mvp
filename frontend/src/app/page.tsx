import { DataLimitationsFooter } from "@/components/data-limitations-footer";
import { CatalystsSection } from "@/components/catalysts-section";
import { FeedSection } from "@/components/feed-section";
import { Header } from "@/components/header";

export default function Home() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <div className="flex flex-col gap-12">
          <CatalystsSection />
          <FeedSection />
        </div>
      </main>
      <DataLimitationsFooter />
    </>
  );
}
