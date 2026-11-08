"use client";

import { useEffect, useState } from "react";

import { api, ApiClientError } from "@/lib/api";
import { clearCredential, getCredential, getWorkspaceId, saveCredential } from "@/lib/auth";
import type { WorkspaceInfo } from "@/lib/types";

/** Paste a workspace API key (or, later, a provider token) to use the app. */
export function ConnectPanel({ onConnected }: { onConnected?: (workspace: WorkspaceInfo | null) => void }) {
  const [credential, setCredential] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getCredential()) return;
    api
      .getWorkspace()
      .then(setWorkspace)
      .catch(() => undefined);
  }, []);

  async function connect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    saveCredential(credential, workspaceId);
    try {
      const info = await api.getWorkspace();
      setWorkspace(info);
      setCredential("");
      onConnected?.(info);
    } catch (caught) {
      clearCredential();
      setError(
        caught instanceof ApiClientError && caught.status === 401
          ? "That key was not accepted."
          : caught instanceof ApiClientError
            ? caught.message
            : "Could not connect.",
      );
    } finally {
      setBusy(false);
    }
  }

  function disconnect() {
    clearCredential();
    setWorkspace(null);
    onConnected?.(null);
  }

  if (workspace && getCredential()) {
    return (
      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
        <p>
          Connected to <strong>{workspace.name}</strong> ({workspace.plan.name} plan
          {workspace.role ? `, ${workspace.role}` : ""}
          {getWorkspaceId() ? `, workspace ${getWorkspaceId()}` : ""}).
        </p>
        <button type="button" onClick={disconnect} className="mt-2 text-xs font-semibold text-emerald-900 underline">
          Disconnect
        </button>
      </section>
    );
  }

  return (
    <form onSubmit={connect} className="rounded-xl border border-slate-200 bg-white p-4 text-sm" aria-label="Connect">
      <h2 className="font-semibold">Connect your workspace</h2>
      <p className="mt-1 text-slate-600">
        Paste a workspace API key. It is kept only for this browser tab and sent to the unMeet API.
      </p>
      <label className="mt-3 block">
        <span className="font-medium">API key</span>
        <input
          type="password"
          autoComplete="off"
          value={credential}
          onChange={(event) => setCredential(event.target.value)}
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
          placeholder="um_…"
        />
      </label>
      <label className="mt-3 block">
        <span className="font-medium">Workspace id (only if you belong to several)</span>
        <input
          inputMode="numeric"
          value={workspaceId}
          onChange={(event) => setWorkspaceId(event.target.value)}
          className="mt-1 w-32 rounded border border-slate-300 px-3 py-2"
        />
      </label>
      {error && (
        <p role="alert" className="mt-2 text-rose-700">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !credential.trim()}
        className="mt-3 rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
      >
        {busy ? "Connecting…" : "Connect"}
      </button>
    </form>
  );
}
