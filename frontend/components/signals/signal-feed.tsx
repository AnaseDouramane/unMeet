"use client";

import { useCallback, useEffect, useState } from "react";

import { ConnectPanel } from "@/components/auth/connect-panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { SignalCard } from "@/components/signals/signal-card";
import { api, ApiClientError } from "@/lib/api";
import type { Signal, SignalFilters, SignalIntent } from "@/lib/types";

const INTENTS: { value: SignalIntent; label: string }[] = [
  { value: "solution_search", label: "Looking for a solution" },
  { value: "competitor_complaint", label: "Competitor complaint" },
  { value: "pain_point", label: "Pain point" },
  { value: "feature_request", label: "Feature request" },
];

export function SignalFeed() {
  const [topic, setTopic] = useState("");
  const [product, setProduct] = useState("");
  const [intents, setIntents] = useState<SignalIntent[]>([]);
  const [minSeverity, setMinSeverity] = useState<number | undefined>(undefined);
  const [filters, setFilters] = useState<SignalFilters>({ limit: 50 });
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsLogin, setNeedsLogin] = useState(false);

  const load = useCallback(async (current: SignalFilters) => {
    setLoading(true);
    setError(null);
    try {
      setSignals((await api.getSignals(current)).items);
      setNeedsLogin(false);
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.status === 401) setNeedsLogin(true);
      setError(caught instanceof ApiClientError ? caught.message : "Signals could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

  function apply(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({
      limit: 50,
      topic: topic.trim() || undefined,
      product: product.trim() ? [product.trim()] : undefined,
      intent: intents.length ? intents : undefined,
      min_severity: minSeverity,
    });
  }

  function toggleIntent(intent: SignalIntent) {
    setIntents((current) =>
      current.includes(intent) ? current.filter((value) => value !== intent) : [...current, intent],
    );
  }

  if (needsLogin) return <ConnectPanel onConnected={() => void load(filters)} />;

  return (
    <>
      <form onSubmit={apply} className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="grid gap-3 md:grid-cols-[2fr_1fr_auto]">
          <label className="grid gap-1 text-sm font-medium">
            Topic
            <input
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. duplicate contacts in the CRM"
              className="rounded-lg border border-slate-300 px-3 py-2 font-normal"
            />
          </label>
          <label className="grid gap-1 text-sm font-medium">
            Product mentioned
            <input
              value={product}
              onChange={(event) => setProduct(event.target.value)}
              placeholder="e.g. HubSpot"
              className="rounded-lg border border-slate-300 px-3 py-2 font-normal"
            />
          </label>
          <label className="grid gap-1 text-sm font-medium">
            Min severity
            <select
              value={minSeverity ?? ""}
              onChange={(event) => setMinSeverity(event.target.value ? Number(event.target.value) : undefined)}
              className="rounded-lg border border-slate-300 px-3 py-2 font-normal"
            >
              <option value="">Any</option>
              <option value="2">2+</option>
              <option value="3">3</option>
            </select>
          </label>
        </div>
        <fieldset className="flex flex-wrap gap-2">
          <legend className="sr-only">Intent</legend>
          {INTENTS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={intents.includes(value)}
              onClick={() => toggleIntent(value)}
              className={`rounded-full border px-3 py-1 text-sm ${
                intents.includes(value)
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
          <div className="ml-auto flex gap-2">
            <a
              href={api.signalsCsvUrl(filters)}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold"
            >
              Export CSV
            </a>
            <button type="submit" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white">
              Apply
            </button>
          </div>
        </fieldset>
      </form>
      <div className="mt-5">
        {loading && <LoadingSkeleton />}
        {!loading && error && <ErrorState message={error} onRetry={() => void load(filters)} />}
        {!loading && !error && signals && !signals.length && (
          <EmptyState title="No signals yet" message="Broaden the filters or run an ingestion first." />
        )}
        {!loading && !error && signals && signals.length > 0 && (
          <div className="grid gap-3">
            {signals.map((signal) => (
              <SignalCard key={signal.id} signal={signal} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
