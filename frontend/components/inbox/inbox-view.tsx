"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ConnectPanel } from "@/components/auth/connect-panel";
import { ReplyDraftPanel } from "@/components/inbox/reply-draft-panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { api, ApiClientError } from "@/lib/api";
import { formatDate } from "@/lib/formatters";
import type { InboxCounts, InboxItem, InboxState, Topic } from "@/lib/types";

const TABS: { state: InboxState; label: string }[] = [
  { state: "new", label: "New" },
  { state: "relevant", label: "Relevant" },
  { state: "replied", label: "Replied" },
  { state: "not_relevant", label: "Not relevant" },
];

const SHORTCUTS: Record<string, InboxState> = { r: "relevant", x: "not_relevant", e: "replied", u: "new" };

export function InboxView() {
  const [tab, setTab] = useState<InboxState>("new");
  const [topicId, setTopicId] = useState<number | undefined>(undefined);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [counts, setCounts] = useState<InboxCounts | null>(null);
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [draftFor, setDraftFor] = useState<number | null>(null);
  const itemsRef = useRef<InboxItem[] | null>(null);
  itemsRef.current = items;

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, newCounts, topicList] = await Promise.all([
        api.getInbox({ state: tab, topic_id: topicId, limit: 50 }),
        api.getInboxCounts(),
        api.getTopics(),
      ]);
      setItems(list.items);
      setCounts(newCounts);
      setTopics(topicList.items);
      setNeedsLogin(false);
      setCursor(0);
      setSelected(new Set());
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.status === 401) setNeedsLogin(true);
      else setError(caught instanceof ApiClientError ? caught.message : "The inbox could not be loaded.");
    }
  }, [tab, topicId]);

  useEffect(() => {
    void load();
  }, [load]);

  const apply = useCallback(
    async (ids: number[], state: InboxState) => {
      if (!ids.length) return;
      try {
        await api.setInboxState(ids, state);
      } catch (caught) {
        setError(caught instanceof ApiClientError ? caught.message : "The change could not be saved.");
        return;
      }
      // The current tab shows a single state, so moved items leave it.
      setItems((current) => (current ? current.filter((item) => !ids.includes(item.signal_id)) : current));
      setSelected(new Set());
      setCursor((value) => Math.max(0, value));
      setCounts((current) => {
        if (!current || !itemsRef.current) return current;
        const next = { ...current };
        for (const item of itemsRef.current) {
          if (!ids.includes(item.signal_id)) continue;
          next[item.state] -= 1;
          next[state] += 1;
        }
        return next;
      });
    },
    [],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const list = itemsRef.current;
      if (!list || list.length === 0) return;
      const current = list[Math.min(cursor, list.length - 1)];
      if (event.key === "j") setCursor((value) => Math.min(value + 1, list.length - 1));
      else if (event.key === "k") setCursor((value) => Math.max(value - 1, 0));
      else if (event.key === " ") {
        event.preventDefault();
        setSelected((value) => {
          const next = new Set(value);
          if (next.has(current.signal_id)) next.delete(current.signal_id);
          else next.add(current.signal_id);
          return next;
        });
      } else if (event.key === "o") window.open(current.url, "_blank", "noopener,noreferrer");
      else if (event.key === "d") setDraftFor(current.signal_id);
      else if (SHORTCUTS[event.key]) {
        const ids = selected.size ? [...selected] : [current.signal_id];
        void apply(ids, SHORTCUTS[event.key]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cursor, selected, apply]);

  if (needsLogin) return <ConnectPanel onConnected={() => void load()} />;
  if (error && !items) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!items) return <LoadingSkeleton />;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Inbox states">
        {TABS.map(({ state, label }) => (
          <button
            key={state}
            role="tab"
            type="button"
            aria-selected={tab === state}
            onClick={() => setTab(state)}
            className={`rounded-full px-3 py-1 text-sm font-medium ${tab === state ? "bg-indigo-700 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200"}`}
          >
            {label}
            {counts ? ` (${counts[state]})` : ""}
          </button>
        ))}
        <select
          aria-label="Topic"
          value={topicId ?? ""}
          onChange={(event) => setTopicId(event.target.value ? Number(event.target.value) : undefined)}
          className="ml-auto rounded border border-slate-300 bg-white px-2 py-1 text-sm"
        >
          <option value="">All topics</option>
          {topics.map((topic) => (
            <option key={topic.id} value={topic.id}>
              {topic.name}
            </option>
          ))}
        </select>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Keys: <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>r</kbd> relevant · <kbd>x</kbd> not relevant · <kbd>e</kbd> replied ·{" "}
        <kbd>u</kbd> back to new · <kbd>space</kbd> select · <kbd>o</kbd> open · <kbd>d</kbd> draft reply
      </p>

      {selected.size > 0 && (
        <div className="mt-3 flex items-center gap-2 rounded bg-slate-100 p-2 text-sm" aria-label="Bulk actions">
          <span>{selected.size} selected</span>
          <button type="button" onClick={() => void apply([...selected], "relevant")} className="rounded bg-white px-2 py-1 ring-1 ring-slate-300">
            Mark relevant
          </button>
          <button type="button" onClick={() => void apply([...selected], "not_relevant")} className="rounded bg-white px-2 py-1 ring-1 ring-slate-300">
            Mark not relevant
          </button>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {error}
        </p>
      )}

      {items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title={tab === "new" ? "Nothing new" : "Nothing here"}
            message={
              tab === "new"
                ? "New conversations that match your topics will appear here. Add topics, or run the onboarding to create them from your website."
                : "Items you mark with this state will appear here."
            }
          />
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {items.map((item, index) => (
            <li
              key={item.signal_id}
              aria-current={index === cursor}
              className={`rounded-xl border bg-white p-4 ${index === cursor ? "border-indigo-500 ring-2 ring-indigo-200" : "border-slate-200"}`}
            >
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  aria-label={`Select ${item.title}`}
                  checked={selected.has(item.signal_id)}
                  onChange={() =>
                    setSelected((value) => {
                      const next = new Set(value);
                      if (next.has(item.signal_id)) next.delete(item.signal_id);
                      else next.add(item.signal_id);
                      return next;
                    })
                  }
                  className="mt-1"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-slate-500">
                    {item.topic_name} · {item.source} · {item.author ?? "anonymous"} · {formatDate(item.published_at)}
                  </p>
                  <p className="mt-1 text-base text-slate-900">{item.pain_quote ? `“${item.pain_quote}”` : item.title}</p>
                  <p className="mt-1 text-sm text-slate-600">
                    <span className="font-medium text-slate-700">Why it matches:</span> {item.relevance_reason}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <a href={item.url} target="_blank" rel="noreferrer" className="font-medium text-indigo-700 hover:underline">
                      Open original
                    </a>
                    <button type="button" onClick={() => void apply([item.signal_id], "relevant")} className="text-emerald-700 underline">
                      Relevant
                    </button>
                    <button type="button" onClick={() => void apply([item.signal_id], "not_relevant")} className="text-rose-700 underline">
                      Not relevant
                    </button>
                    <button type="button" onClick={() => setDraftFor(item.signal_id)} className="text-indigo-700 underline">
                      Draft reply
                    </button>
                  </div>
                  {draftFor === item.signal_id && (
                    <ReplyDraftPanel signalId={item.signal_id} onClose={() => setDraftFor(null)} />
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
