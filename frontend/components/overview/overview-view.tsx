"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ConnectPanel } from "@/components/auth/connect-panel";
import { RunFunnel } from "@/components/overview/run-funnel";
import { ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { api, ApiClientError } from "@/lib/api";
import { getCredential } from "@/lib/auth";
import type { Overview } from "@/lib/types";

function when(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function Tile({ label, value, hint, href }: { label: string; value: string | number; hint?: string; href?: string }) {
  const body = (
    <>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </>
  );
  return href ? (
    <Link href={href} className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-indigo-400">
      {body}
    </Link>
  ) : (
    <div className="rounded-xl border border-slate-200 bg-white p-4">{body}</div>
  );
}

export function OverviewView() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [hasKey, setHasKey] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    setHasKey(Boolean(getCredential()));
    try {
      setData(await api.getOverview());
      setNeedsLogin(false);
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.status === 401) setNeedsLogin(true);
      else setError(caught instanceof ApiClientError ? caught.message : "The overview could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (needsLogin) return <ConnectPanel onConnected={() => void load()} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!data) return <LoadingSkeleton />;

  const last = data.runs[0];
  const totalMatched = data.topics.reduce((sum, topic) => sum + topic.matched, 0);
  const fresh = last ? Math.max(last.acquired - last.skipped, 0) : 0;
  const allDropped = Boolean(last) && fresh > 0 && last.gated_out >= fresh;

  return (
    <div className="space-y-8">
      {!hasKey && (
        <section aria-label="Connect your workspace" className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50 p-5">
          <p className="text-sm text-indigo-950">
            You are looking at the empty <strong>{data.workspace.name}</strong> workspace because no key is set. Paste the key
            the setup printed (it starts with <code>um_</code>) to see your own workspace.
          </p>
          <ConnectPanel onConnected={() => void load()} />
        </section>
      )}
      <section aria-label="What we understood" className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold">{data.workspace.name}</h2>
        {data.workspace.product_summary ? (
          <p className="mt-1 text-slate-700">{data.workspace.product_summary}</p>
        ) : (
          <p className="mt-1 text-sm text-slate-500">
            No product description yet. Run the setup with your website (<code>--site</code>) or use Set up.
          </p>
        )}
        {data.workspace.website_url && (
          <a href={data.workspace.website_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-indigo-700 hover:underline">
            {data.workspace.website_url}
          </a>
        )}
      </section>

      <section aria-label="Inbox" className="grid gap-3 sm:grid-cols-4">
        <Tile label="New in inbox" value={data.inbox.new} hint="Waiting for you" href="/inbox" />
        <Tile label="Relevant" value={data.inbox.relevant} />
        <Tile label="Replied" value={data.inbox.replied} />
        <Tile label="Not relevant" value={data.inbox.not_relevant} />
      </section>

      <section aria-label="Last run">
        <h2 className="text-lg font-semibold">Last search</h2>
        {!last ? (
          <p className="mt-2 rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-600">
            No search has run yet. Run <code>python -m scripts.prototype --owner you@example.com --site https://your-site.com</code>.
          </p>
        ) : (
          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-5">
            <p className="mb-4 text-xs text-slate-500">
              {when(last.started_at)} · {last.source} · {last.duration_seconds}s
            </p>
            {last.status === "error" && (
              <p role="alert" className="mb-4 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
                The search stopped with an error: {last.error ?? "unknown"}. The numbers below are what was saved before it.
              </p>
            )}
            <RunFunnel run={last} />
            {last.matched === 0 && last.status === "ok" && (
              <div className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                <p className="font-medium">Nothing matched this time. Things to try:</p>
                {allDropped && (
                  <p className="mt-1">
                    All {fresh} new post{fresh === 1 ? " was" : "s were"} too far from your topics, so the AI did not read{" "}
                    {fresh === 1 ? "it" : "them"} (this costs nothing). Clearer topic descriptions and phrases help.
                  </p>
                )}
                <ul className="mt-1 list-disc pl-5">
                  <li>Look further back: add <code>--days 365</code> to the setup command.</li>
                  <li>
                    In <Link href="/topics" className="underline">Topics</Link>, write phrases the way a person would (&ldquo;alternative to X&rdquo;,
                    &ldquo;looking for a tool to…&rdquo;) and add competitor names.
                  </li>
                  <li>If it stays empty, Hacker News has no conversations on this subject: it is a result, not a bug.</li>
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <section aria-label="Topics">
        <h2 className="text-lg font-semibold">Topics</h2>
        <p className="text-sm text-slate-600">
          {totalMatched} conversation{totalMatched === 1 ? "" : "s"} matched so far. The phrases decide what is searched.
        </p>
        <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Topic</th>
                <th className="px-4 py-2">Phrases searched</th>
                <th className="px-4 py-2 text-right">Matched</th>
                <th className="px-4 py-2 text-right">New</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.topics.map((topic) => (
                <tr key={topic.id}>
                  <td className="px-4 py-2 align-top">
                    <p className="font-medium text-slate-900">{topic.name}</p>
                    {topic.description && <p className="text-xs text-slate-500">{topic.description}</p>}
                  </td>
                  <td className="px-4 py-2 align-top">
                    <div className="flex flex-wrap gap-1">
                      {[...topic.keywords, ...topic.products].map((phrase) => (
                        <span key={phrase} className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-700">
                          {phrase}
                        </span>
                      ))}
                      {topic.keywords.length + topic.products.length === 0 && (
                        <span className="text-xs text-amber-800">No phrases: nothing is searched for this topic</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right align-top tabular-nums">{topic.matched}</td>
                  <td className="px-4 py-2 text-right align-top tabular-nums">{topic.new}</td>
                </tr>
              ))}
              {data.topics.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-4 text-slate-500">
                    No topics yet: run the setup or create one in Topics.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label="AI usage" className="grid gap-3 sm:grid-cols-3">
        <Tile label="AI requests this month" value={data.usage.calls} hint="Setup and reply drafts for this workspace" />
        <Tile label="Tokens this month" value={data.usage.total_tokens.toLocaleString()} />
        <Tile
          label="Spend this month"
          value={data.usage.spent_usd === null ? "Unknown" : `$${data.usage.spent_usd.toFixed(2)}`}
          hint={data.usage.spent_usd === null ? "Set LLM prices in .env to see it" : `Budget $${data.usage.llm_budget_usd}`}
        />
      </section>

      {data.runs.length > 1 && (
        <section aria-label="Recent runs">
          <h2 className="text-lg font-semibold">Recent searches</h2>
          <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2">When</th>
                  <th className="px-4 py-2 text-right">Found</th>
                  <th className="px-4 py-2 text-right">Read by AI</th>
                  <th className="px-4 py-2 text-right">AI requests</th>
                  <th className="px-4 py-2 text-right">Matched</th>
                  <th className="px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.runs.map((run, index) => (
                  <tr key={`${run.started_at}-${index}`}>
                    <td className="px-4 py-2">{when(run.started_at)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{run.acquired}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{Math.max(run.acquired - run.skipped - run.gated_out, 0)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{run.llm_requests}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{run.matched}</td>
                    <td className="px-4 py-2">{run.status === "ok" ? "OK" : `Error: ${run.error ?? "unknown"}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
