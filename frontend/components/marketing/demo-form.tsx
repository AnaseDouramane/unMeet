"use client";

import { useState } from "react";

import { api, ApiClientError } from "@/lib/api";
import { formatDate } from "@/lib/formatters";
import type { DemoResult } from "@/lib/types";

export function DemoForm() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<DemoResult | null>(null);
  const [error, setError] = useState<{ message: string; code?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.runDemo(url.trim()));
    } catch (caught) {
      setError(
        caught instanceof ApiClientError
          ? { message: caught.message, code: caught.code }
          : { message: "The demo could not be reached." },
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={run} aria-label="Live demo" className="flex flex-col gap-2 sm:flex-row">
        <input
          type="url"
          required
          aria-label="Your website"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://yourproduct.com"
          className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-3"
        />
        <button type="submit" disabled={busy || !url.trim()} className="rounded bg-indigo-700 px-5 py-3 font-semibold text-white disabled:opacity-50">
          {busy ? "Reading your site…" : "Show me real conversations"}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error.code === "demo_disabled"
            ? "The live demo is not available right now. Request access below and we will set it up with you."
            : error.message}
        </p>
      )}

      {result && (
        <section aria-label="Demo result" className="mt-5 text-sm">
          <p className="text-slate-700">
            <strong>What we understood:</strong> {result.product_summary}
          </p>
          {result.competitors.length > 0 && (
            <p className="mt-1 text-slate-600">
              <strong>Competitors:</strong> {result.competitors.join(", ")}
            </p>
          )}
          {result.signals.length === 0 ? (
            <p className="mt-4 rounded border border-dashed border-slate-300 p-4 text-slate-600">
              We have no matching conversations in our current dataset yet. Tracked topics ({result.topics.join(", ")}) fill
              your inbox as new posts appear.
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {result.signals.map((signal) => (
                <li key={signal.url} className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs text-slate-500">
                    {signal.source} · {formatDate(signal.published_at)}
                  </p>
                  <p className="mt-1 text-base text-slate-900">{signal.quote ? `“${signal.quote}”` : signal.title}</p>
                  <a href={signal.url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs font-medium text-indigo-700 hover:underline">
                    Open original
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
