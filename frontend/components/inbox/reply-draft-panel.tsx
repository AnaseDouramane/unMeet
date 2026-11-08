"use client";

import { useEffect, useState } from "react";

import { api, ApiClientError } from "@/lib/api";
import type { ReplyDraft } from "@/lib/types";

export function ReplyDraftPanel({ signalId, onClose }: { signalId: number; onClose: () => void }) {
  const [draft, setDraft] = useState<ReplyDraft | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .getReplyDraft(signalId)
      .then((result) => {
        if (!active) return;
        setDraft(result);
        setText(result.draft);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiClientError ? caught.message : "The draft could not be created.");
      });
    return () => {
      active = false;
    };
  }, [signalId]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setError("Copy failed: select the text and copy it manually.");
    }
  }

  return (
    <section role="dialog" aria-label="Reply draft" className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold">Reply draft</h3>
        <button type="button" onClick={onClose} className="text-xs font-semibold text-slate-600 underline">
          Close
        </button>
      </div>
      {!draft && !error && <p className="mt-2 text-slate-600">Writing a draft…</p>}
      {error && (
        <p role="alert" className="mt-2 text-rose-700">
          {error}
        </p>
      )}
      {draft && (
        <>
          <textarea
            aria-label="Draft text"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setCopied(false);
            }}
            rows={7}
            className="mt-2 w-full rounded border border-slate-300 bg-white p-2"
          />
          {draft.disclosure_added && (
            <p className="mt-1 text-xs text-amber-800">
              The model did not disclose your affiliation, so a disclosure line was added. Keep it.
            </p>
          )}
          <p className="mt-2 text-xs text-slate-700">
            <strong>Community rules:</strong> {draft.community_rules}
          </p>
          <p className="mt-1 text-xs text-slate-600">{draft.note}</p>
          <button type="button" onClick={copy} className="mt-3 rounded bg-indigo-700 px-3 py-2 font-semibold text-white">
            {copied ? "Copied" : "Copy"}
          </button>
        </>
      )}
    </section>
  );
}
