import Link from "next/link";

import { SignalCard } from "@/components/signals/signal-card";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { api, ApiClientError } from "@/lib/api";
import type { Signal } from "@/lib/types";

export default async function TopicSignalsPage({ params }: { params: Promise<{ topicId: string }> }) {
  const { topicId } = await params;
  let signals: Signal[] = [];
  let error: string | null = null;
  try {
    signals = (await api.getTopicSignals(topicId)).items;
  } catch (caught) {
    error = caught instanceof ApiClientError ? caught.message : "Signals could not be loaded.";
  }
  return (
    <>
      <Link href="/topics" className="text-sm text-indigo-700 hover:underline">← All topics</Link>
      <div className="mt-3">
        <PageHeader title="Topic signals" description="Most similar first." />
      </div>
      {error && <ErrorState message={error} />}
      {!error && !signals.length && <EmptyState title="No matching signals" message="New data is matched after each ingestion run." />}
      {!error && signals.length > 0 && (
        <div className="grid gap-3">
          {signals.map((signal) => <SignalCard key={signal.id} signal={signal} />)}
        </div>
      )}
    </>
  );
}
