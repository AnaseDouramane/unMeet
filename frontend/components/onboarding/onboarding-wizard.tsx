"use client";

import Link from "next/link";
import { useState } from "react";

import { ConnectPanel } from "@/components/auth/connect-panel";
import { api, ApiClientError } from "@/lib/api";
import type { ConfirmResult, Proposal, ProposalTopic } from "@/lib/types";

type Step = "url" | "review" | "done";

export function OnboardingWizard() {
  const [step, setStep] = useState<Step>("url");
  const [url, setUrl] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [topics, setTopics] = useState<ProposalTopic[]>([]);
  const [summary, setSummary] = useState("");
  const [result, setResult] = useState<ConfirmResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);

  function fail(caught: unknown, fallback: string) {
    if (caught instanceof ApiClientError && caught.status === 401) setNeedsLogin(true);
    else setError(caught instanceof ApiClientError ? caught.message : fallback);
  }

  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const found = await api.analyzeSite(url.trim());
      setProposal(found);
      setTopics(found.topics);
      setSummary(found.product_summary);
      setNeedsLogin(false);
      setStep("review");
    } catch (caught) {
      fail(caught, "The site could not be analysed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api.confirmOnboarding({
          website_url: proposal?.source_url,
          product_summary: summary.trim() || undefined,
          topics,
        }),
      );
      setStep("done");
    } catch (caught) {
      fail(caught, "The topics could not be created.");
    } finally {
      setBusy(false);
    }
  }

  function updateTopic(index: number, patch: Partial<ProposalTopic>) {
    setTopics((current) => current.map((topic, i) => (i === index ? { ...topic, ...patch } : topic)));
  }

  if (needsLogin) return <ConnectPanel onConnected={() => setNeedsLogin(false)} />;

  if (step === "url") {
    return (
      <form onSubmit={analyze} className="max-w-xl space-y-3" aria-label="Analyse your website">
        <label className="block text-sm">
          <span className="font-medium">Your website</span>
          <input
            type="url"
            required
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://yourproduct.com"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
          />
        </label>
        <p className="text-xs text-slate-600">
          We read the public page, infer what you sell and who competes with you, and propose topics to
          monitor. Nothing is saved until you confirm.
        </p>
        {error && (
          <p role="alert" className="text-sm text-rose-700">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || !url.trim()} className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50">
          {busy ? "Reading your site…" : "Analyse"}
        </button>
      </form>
    );
  }

  if (step === "done" && result) {
    return (
      <section className="max-w-xl space-y-3 text-sm">
        <h2 className="text-lg font-semibold">
          {result.created.length} topic{result.created.length === 1 ? "" : "s"} created
        </h2>
        {result.skipped.length > 0 && (
          <ul className="rounded border border-amber-300 bg-amber-50 p-3 text-amber-900">
            {result.skipped.map((item) => (
              <li key={item.name}>
                <strong>{item.name}</strong> was skipped: {item.reason}
              </li>
            ))}
          </ul>
        )}
        <p className="text-slate-600">Matching conversations will appear in your inbox as they are found.</p>
        <Link href="/inbox" className="inline-block rounded bg-indigo-700 px-4 py-2 font-semibold text-white">
          Go to the inbox
        </Link>
      </section>
    );
  }

  return (
    <section className="max-w-3xl space-y-5 text-sm">
      <div>
        <label className="block">
          <span className="font-medium">What you sell</span>
          <textarea
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            rows={2}
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
          />
        </label>
        {proposal?.icp && (
          <p className="mt-1 text-slate-600">
            <strong>Buyer:</strong> {proposal.icp}
          </p>
        )}
        {proposal && proposal.competitors.length > 0 && (
          <p className="mt-1 text-slate-600">
            <strong>Competitors found:</strong> {proposal.competitors.join(", ")}
          </p>
        )}
      </div>

      <div>
        <h2 className="font-semibold">Topics to monitor</h2>
        <p className="text-slate-600">Edit or remove anything that is not right.</p>
        <ul className="mt-3 space-y-3">
          {topics.map((topic, index) => (
            <li key={index} className="rounded-xl border border-slate-200 bg-white p-3">
              <input
                aria-label={`Topic ${index + 1} name`}
                value={topic.name}
                onChange={(event) => updateTopic(index, { name: event.target.value })}
                className="w-full rounded border border-slate-300 px-2 py-1 font-medium"
              />
              <textarea
                aria-label={`Topic ${index + 1} description`}
                value={topic.description}
                onChange={(event) => updateTopic(index, { description: event.target.value })}
                rows={2}
                className="mt-2 w-full rounded border border-slate-300 px-2 py-1"
              />
              <label className="mt-2 block text-xs text-slate-600">
                Phrases we will search for (comma separated)
                <input
                  aria-label={`Topic ${index + 1} phrases`}
                  value={(topic.keywords ?? []).join(", ")}
                  onChange={(event) =>
                    updateTopic(index, {
                      keywords: event.target.value.split(",").map((value) => value.trim()).filter(Boolean),
                    })
                  }
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                />
              </label>
              <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
                <span>{topic.products.length ? `Mentions: ${topic.products.join(", ")}` : "No specific product"}</span>
                <button
                  type="button"
                  onClick={() => setTopics((current) => current.filter((_, i) => i !== index))}
                  className="text-rose-700 underline"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {error && (
        <p role="alert" className="text-rose-700">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => void confirm()}
          disabled={busy || topics.length === 0 || topics.some((topic) => !topic.name.trim() || !topic.description.trim())}
          className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Creating…" : `Create ${topics.length} topic${topics.length === 1 ? "" : "s"}`}
        </button>
        <button type="button" onClick={() => setStep("url")} className="rounded px-4 py-2 text-slate-700 ring-1 ring-slate-300">
          Start over
        </button>
      </div>
    </section>
  );
}
