"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState } from "@/components/ui/states";
import { api, ApiClientError } from "@/lib/api";
import { formatDate } from "@/lib/formatters";
import type { SignalIntent, Topic, TopicInput } from "@/lib/types";

const API_KEY_STORAGE = "unmeet.apiKey";

const INTENTS: { value: SignalIntent; label: string }[] = [
  { value: "solution_search", label: "Looking for a solution" },
  { value: "competitor_complaint", label: "Competitor complaint" },
  { value: "pain_point", label: "Pain point" },
  { value: "feature_request", label: "Feature request" },
];

function readApiKey(): string {
  try {
    return window.sessionStorage.getItem(API_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof ApiClientError ? caught.message : fallback;
}

export function TopicManager() {
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [products, setProducts] = useState("");
  const [webhook, setWebhook] = useState("");
  const [intents, setIntents] = useState<SignalIntent[]>([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      setTopics((await api.getTopics()).items);
    } catch (caught) {
      setError(errorMessage(caught, "Topics could not be loaded."));
    }
  }, []);

  useEffect(() => {
    setApiKey(readApiKey());
    void load();
  }, [load]);

  function rememberApiKey(value: string) {
    setApiKey(value);
    try {
      window.sessionStorage.setItem(API_KEY_STORAGE, value);
    } catch {
      // Storage can be unavailable (private mode); the key then lives only in memory.
    }
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input: TopicInput = {
      name: name.trim(),
      description: description.trim() || undefined,
      intents,
      products: products.split(",").map((value) => value.trim()).filter(Boolean),
      webhook_url: webhook.trim() || undefined,
    };
    if (!input.name) {
      setFormError("Give the topic a name.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      await api.createTopic(input, apiKey || undefined);
      setName("");
      setDescription("");
      setProducts("");
      setWebhook("");
      setIntents([]);
      await load();
    } catch (caught) {
      setFormError(errorMessage(caught, "The topic could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function remove(topic: Topic) {
    try {
      await api.deleteTopic(topic.id, apiKey || undefined);
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "The topic could not be deleted."));
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <section aria-labelledby="topics-heading">
        <h2 id="topics-heading" className="sr-only">Tracked topics</h2>
        {error && <ErrorState message={error} onRetry={() => void load()} />}
        {!error && topics && !topics.length && (
          <EmptyState title="No topics yet" message="Create one to follow a problem space over time." />
        )}
        {!error && topics && topics.length > 0 && (
          <ul className="grid gap-3">
            {topics.map((topic) => (
              <li key={topic.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Link href={`/topics/${topic.id}`} className="font-semibold hover:underline">
                      {topic.name}
                    </Link>
                    {topic.description && <p className="mt-1 text-sm text-slate-600">{topic.description}</p>}
                  </div>
                  <button
                    type="button"
                    onClick={() => void remove(topic)}
                    className="text-sm text-slate-500 hover:text-rose-700"
                    aria-label={`Delete ${topic.name}`}
                  >
                    Delete
                  </button>
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  {[...topic.intents, ...topic.products].join(" · ") || "Semantic match only"}
                  {topic.has_webhook && ` · webhook · last sent ${formatDate(topic.last_delivered_at)}`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <form onSubmit={create} className="grid h-fit gap-3 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold">New topic</h2>
        <label className="grid gap-1 text-sm font-medium">
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 font-normal" />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Describe the pain
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Sales reps waste hours cleaning CRM data"
            className="rounded-lg border border-slate-300 px-3 py-2 font-normal"
          />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Products (comma separated)
          <input value={products} onChange={(e) => setProducts(e.target.value)} placeholder="HubSpot, Salesforce" className="rounded-lg border border-slate-300 px-3 py-2 font-normal" />
        </label>
        <fieldset className="grid gap-1 text-sm">
          <legend className="font-medium">Intents</legend>
          {INTENTS.map(({ value, label }) => (
            <label key={value} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={intents.includes(value)}
                onChange={() =>
                  setIntents((current) =>
                    current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                  )
                }
              />
              {label}
            </label>
          ))}
        </fieldset>
        <label className="grid gap-1 text-sm font-medium">
          Webhook (optional)
          <input value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://api.clay.com/…" className="rounded-lg border border-slate-300 px-3 py-2 font-normal" />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          API key
          <input type="password" value={apiKey} onChange={(e) => rememberApiKey(e.target.value)} autoComplete="off" className="rounded-lg border border-slate-300 px-3 py-2 font-normal" />
        </label>
        {formError && <p role="alert" className="text-sm text-rose-700">{formError}</p>}
        <button type="submit" disabled={saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
          {saving ? "Saving…" : "Create topic"}
        </button>
      </form>
    </div>
  );
}
