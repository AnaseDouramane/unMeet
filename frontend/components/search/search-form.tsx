"use client";

import { useState } from "react";

import { api, ApiClientError } from "@/lib/api";
import { excerpt } from "@/lib/formatters";
import type { PublicDocument } from "@/lib/types";
import { EmptyState, ErrorState } from "@/components/ui/states";

export function SearchForm() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PublicDocument[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) { setError("Enter a search query before submitting."); return; }
    setLoading(true); setError(null);
    try { setResults((await api.search(query.trim())).items); } catch (caught) { setError(caught instanceof ApiClientError ? caught.message : "Search failed."); } finally { setLoading(false); }
  }
  return <><form onSubmit={submit} className="flex gap-2"><label className="sr-only" htmlFor="search-query">Search problems</label><input id="search-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Describe a problem or need" className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2" /><button type="submit" disabled={loading} className="rounded-lg bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-60">{loading ? "Searching…" : "Search"}</button></form>{error && <div className="mt-5"><ErrorState message={error} onRetry={() => setError(null)} /></div>}{results && !results.length && <div className="mt-5"><EmptyState title="No matching problems" message="Try a more specific query." /></div>}{results && results.length > 0 && <div className="mt-5 grid gap-3">{results.map((result) => <article key={result.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex justify-between gap-3"><h2 className="font-semibold">{result.title}</h2><span className="text-xs text-slate-500">{result.source}</span></div><p className="mt-2 text-sm text-slate-600">{excerpt(result.body)}</p>{result.url && <a className="mt-3 inline-block text-sm font-medium text-indigo-700 hover:underline" href={result.url} target="_blank" rel="noreferrer">Open original post</a>}</article>)}</div>}</>;
}
