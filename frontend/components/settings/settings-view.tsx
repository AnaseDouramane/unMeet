"use client";

import { useCallback, useEffect, useState } from "react";

import { ConnectPanel } from "@/components/auth/connect-panel";
import { ErrorState } from "@/components/ui/states";
import { api, ApiClientError } from "@/lib/api";
import { formatDate } from "@/lib/formatters";
import type { ApiKeyCreated, ApiKeyInfo, ChannelInfo, Member, WorkspaceInfo } from "@/lib/types";

function message(caught: unknown, fallback: string) {
  return caught instanceof ApiClientError ? caught.message : fallback;
}

export function SettingsView() {
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const info = await api.getWorkspace();
      setWorkspace(info);
      setNeedsLogin(false);
      setMembers(await api.getMembers());
      if (info.role === "owner" || info.role === "admin") {
        setKeys(await api.getApiKeys());
        setChannels(await api.getChannels());
      }
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.status === 401) setNeedsLogin(true);
      else setError(message(caught, "Settings could not be loaded."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<unknown>, fallback: string) {
    setError(null);
    try {
      await action();
      await load();
    } catch (caught) {
      setError(message(caught, fallback));
    }
  }

  if (needsLogin || !workspace) {
    return (
      <div className="max-w-xl space-y-4">
        {error && !needsLogin && <ErrorState message={error} onRetry={() => void load()} />}
        <ConnectPanel onConnected={() => void load()} />
      </div>
    );
  }

  const manager = workspace.role === "owner" || workspace.role === "admin";

  return (
    <div className="max-w-3xl space-y-8 text-sm">
      <ConnectPanel onConnected={() => void load()} />
      {error && (
        <p role="alert" className="text-rose-700">
          {error}
        </p>
      )}

      <section aria-label="Plan">
        <h2 className="text-lg font-semibold">Plan: {workspace.plan.name}</h2>
        <p className="text-slate-600">
          Topics {workspace.topics_used ?? 0}/{workspace.plan.max_topics} · Seats {workspace.seats_used ?? 0}/
          {workspace.plan.max_seats} · Slack/webhooks {workspace.plan.webhooks ? "included" : "not included"} · Daily digest{" "}
          {workspace.plan.daily_digest ? "included" : "weekly only"}
        </p>
      </section>

      <section aria-label="Members">
        <h2 className="text-lg font-semibold">Members</h2>
        <ul className="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {members.map((member) => (
            <li key={member.user_id} className="flex items-center justify-between px-3 py-2">
              <span>
                {member.email} <span className="text-xs text-slate-500">({member.role})</span>
              </span>
              {manager && (
                <button
                  type="button"
                  onClick={() => void run(() => api.removeMember(member.user_id), "The member could not be removed.")}
                  className="text-xs text-rose-700 underline"
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
        {manager && <AddMember onAdd={(email, role) => run(() => api.addMember(email, role), "The member could not be added.")} />}
      </section>

      {manager && (
        <>
          <section aria-label="API keys">
            <h2 className="text-lg font-semibold">API keys</h2>
            {newKey && (
              <p role="status" className="mt-2 rounded border border-emerald-300 bg-emerald-50 p-3">
                Copy your new key now, it will not be shown again: <code className="break-all font-semibold">{newKey.key}</code>
              </p>
            )}
            <ul className="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
              {keys.map((key) => (
                <li key={key.id} className="flex items-center justify-between px-3 py-2">
                  <span>
                    {key.name} <code className="text-xs text-slate-500">um_{key.prefix}_…</code>{" "}
                    <span className="text-xs text-slate-500">
                      {key.revoked_at ? "revoked" : key.last_used_at ? `used ${formatDate(key.last_used_at)}` : "never used"}
                    </span>
                  </span>
                  {!key.revoked_at && (
                    <button
                      type="button"
                      onClick={() => void run(() => api.revokeApiKey(key.id), "The key could not be revoked.")}
                      className="text-xs text-rose-700 underline"
                    >
                      Revoke
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <NewKeyForm
              onCreate={async (name) => {
                setError(null);
                try {
                  setNewKey(await api.createApiKey(name));
                  await load();
                } catch (caught) {
                  setError(message(caught, "The key could not be created."));
                }
              }}
            />
          </section>

          <section aria-label="Deliveries">
            <h2 className="text-lg font-semibold">Deliveries</h2>
            <ul className="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
              {channels.map((channel) => (
                <li key={channel.id} className="flex items-center justify-between px-3 py-2">
                  <span>
                    {channel.kind} · {channel.target} · {channel.frequency}
                    {channel.last_error && <span className="ml-2 text-xs text-rose-700">last error: {channel.last_error}</span>}
                  </span>
                  <button
                    type="button"
                    onClick={() => void run(() => api.removeChannel(channel.id), "The channel could not be removed.")}
                    className="text-xs text-rose-700 underline"
                  >
                    Remove
                  </button>
                </li>
              ))}
              {channels.length === 0 && <li className="px-3 py-2 text-slate-500">No digests configured.</li>}
            </ul>
            <AddChannel onAdd={(input) => run(() => api.addChannel(input), "The channel could not be added.")} />
          </section>
        </>
      )}
    </div>
  );
}

function AddMember({ onAdd }: { onAdd: (email: string, role: Member["role"]) => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Member["role"]>("member");
  return (
    <form
      className="mt-3 flex flex-wrap gap-2"
      onSubmit={async (event) => {
        event.preventDefault();
        await onAdd(email, role);
        setEmail("");
      }}
    >
      <input aria-label="Member email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="teammate@company.com" className="rounded border border-slate-300 px-2 py-1" />
      <select aria-label="Member role" value={role} onChange={(event) => setRole(event.target.value as Member["role"])} className="rounded border border-slate-300 px-2 py-1">
        <option value="member">Member</option>
        <option value="admin">Admin</option>
      </select>
      <button type="submit" className="rounded bg-indigo-700 px-3 py-1 font-semibold text-white">
        Add member
      </button>
    </form>
  );
}

function NewKeyForm({ onCreate }: { onCreate: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  return (
    <form
      className="mt-3 flex gap-2"
      onSubmit={async (event) => {
        event.preventDefault();
        await onCreate(name);
        setName("");
      }}
    >
      <input aria-label="Key name" required value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Clay integration" className="rounded border border-slate-300 px-2 py-1" />
      <button type="submit" className="rounded bg-indigo-700 px-3 py-1 font-semibold text-white">
        Create key
      </button>
    </form>
  );
}

function AddChannel({ onAdd }: { onAdd: (input: { kind: "email" | "slack"; target: string; frequency: "daily" | "weekly" }) => Promise<void> }) {
  const [kind, setKind] = useState<"email" | "slack">("email");
  const [target, setTarget] = useState("");
  const [frequency, setFrequency] = useState<"daily" | "weekly">("daily");
  return (
    <form
      className="mt-3 flex flex-wrap gap-2"
      onSubmit={async (event) => {
        event.preventDefault();
        await onAdd({ kind, target, frequency });
        setTarget("");
      }}
    >
      <select aria-label="Channel type" value={kind} onChange={(event) => setKind(event.target.value as "email" | "slack")} className="rounded border border-slate-300 px-2 py-1">
        <option value="email">Email</option>
        <option value="slack">Slack webhook</option>
      </select>
      <input aria-label="Channel target" required value={target} onChange={(event) => setTarget(event.target.value)} placeholder={kind === "email" ? "you@company.com" : "https://hooks.slack.com/services/…"} className="min-w-64 rounded border border-slate-300 px-2 py-1" />
      <select aria-label="Frequency" value={frequency} onChange={(event) => setFrequency(event.target.value as "daily" | "weekly")} className="rounded border border-slate-300 px-2 py-1">
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
      </select>
      <button type="submit" className="rounded bg-indigo-700 px-3 py-1 font-semibold text-white">
        Add
      </button>
    </form>
  );
}
