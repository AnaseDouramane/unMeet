import type {
  AnalyticsSummaryResponse,
  ClusterDetailResponse,
  ClusterListResponse,
  ClusterSort,
  OpportunityListResponse,
  SearchResponse,
  SignalFilters,
  SignalListResponse,
  Topic,
  TopicInput,
  TopicListResponse,
  TrendPeriod,
  TrendStatus,
  TrendsResponse,
  ApiKeyCreated,
  ApiKeyInfo,
  ChannelInfo,
  ChannelInput,
  ConfirmResult,
  Overview,
  DemoResult,
  Report,
  ReportSummary,
  InboxCounts,
  InboxListResponse,
  InboxState,
  Member,
  PlanInfo,
  Proposal,
  ProposalTopic,
  ReplyDraft,
  WorkspaceInfo,
} from "@/lib/types";
import { getCredential, getWorkspaceId } from "@/lib/auth";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

type QueryValue = string | number | string[] | undefined;

export function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!baseUrl) {
    throw new ApiClientError(
      "NEXT_PUBLIC_API_BASE_URL is not configured. Copy .env.example to .env.local and set it.",
    );
  }
  return baseUrl.replace(/\/$/, "");
}

export function buildUrl(path: string, parameters?: Record<string, QueryValue>): URL {
  const url = new URL(`${getApiBaseUrl()}${path}`);
  for (const [key, value] of Object.entries(parameters ?? {})) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, item));
    else url.searchParams.set(key, String(value));
  }
  return url;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  apiKey?: string;
}

async function request<T>(
  path: string,
  parameters?: Record<string, QueryValue>,
  options: RequestOptions = {},
): Promise<T> {
  const url = buildUrl(path, parameters);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const credential = options.apiKey || getCredential();
  if (credential) headers.Authorization = `Bearer ${credential}`;
  const workspaceId = getWorkspaceId();
  if (credential && workspaceId) headers["X-Workspace-ID"] = workspaceId;
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    });
  } catch {
    throw new ApiClientError("The API could not be reached. Check that the backend is running.");
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { code?: string; message?: string }
      | null;
    throw new ApiClientError(
      payload?.message ?? "The API returned an unexpected response.",
      response.status,
      payload?.code,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function signalParameters(filters: SignalFilters): Record<string, QueryValue> {
  return { ...filters };
}

export const api = {
  getSummary: () => request<AnalyticsSummaryResponse>("/api/v1/analytics/summary"),
  getOpportunities: (limit = 10, status?: TrendStatus) =>
    request<OpportunityListResponse>("/api/v1/opportunities", { limit, status }),
  getTrends: (period: TrendPeriod = "day", limit?: number) =>
    request<TrendsResponse>("/api/v1/trends", { period, limit }),
  getClusters: (options: {
    limit?: number;
    offset?: number;
    status?: TrendStatus;
    sort_by?: ClusterSort;
  }) => request<ClusterListResponse>("/api/v1/clusters", options),
  getCluster: (clusterId: string | number) =>
    request<ClusterDetailResponse>(`/api/v1/clusters/${clusterId}`),
  search: (query: string, limit = 10) => request<SearchResponse>("/api/v1/search", { q: query, limit }),
  getSignals: (filters: SignalFilters = {}) =>
    request<SignalListResponse>("/api/v1/signals", signalParameters(filters)),
  signalsCsvUrl: (filters: SignalFilters = {}) =>
    buildUrl("/api/v1/signals.csv", signalParameters({ ...filters, limit: 500 })).toString(),
  getTopics: () => request<TopicListResponse>("/api/v1/topics"),
  getTopicSignals: (topicId: string | number, limit = 50) =>
    request<SignalListResponse>(`/api/v1/topics/${topicId}/signals`, { limit }),
  createTopic: (input: TopicInput, apiKey?: string) =>
    request<Topic>("/api/v1/topics", undefined, { method: "POST", body: input, apiKey }),
  deleteTopic: (topicId: number, apiKey?: string) =>
    request<void>(`/api/v1/topics/${topicId}`, undefined, { method: "DELETE", apiKey }),

  // Workspace
  getPlans: () => request<PlanInfo[]>("/api/v1/plans"),
  getWorkspace: () => request<WorkspaceInfo>("/api/v1/workspace"),
  getOverview: () => request<Overview>("/api/v1/workspace/overview"),
  getMembers: () => request<Member[]>("/api/v1/workspace/members"),
  addMember: (email: string, role: Member["role"]) =>
    request<Member>("/api/v1/workspace/members", undefined, { method: "POST", body: { email, role } }),
  removeMember: (userId: number) =>
    request<void>(`/api/v1/workspace/members/${userId}`, undefined, { method: "DELETE" }),
  getApiKeys: () => request<ApiKeyInfo[]>("/api/v1/workspace/api-keys"),
  createApiKey: (name: string) =>
    request<ApiKeyCreated>("/api/v1/workspace/api-keys", undefined, { method: "POST", body: { name } }),
  revokeApiKey: (keyId: number) =>
    request<void>(`/api/v1/workspace/api-keys/${keyId}`, undefined, { method: "DELETE" }),
  getChannels: () => request<ChannelInfo[]>("/api/v1/workspace/channels"),
  addChannel: (input: ChannelInput) =>
    request<ChannelInfo>("/api/v1/workspace/channels", undefined, { method: "POST", body: input }),
  removeChannel: (channelId: number) =>
    request<void>(`/api/v1/workspace/channels/${channelId}`, undefined, { method: "DELETE" }),

  // Inbox
  getInbox: (options: { state?: InboxState | "all"; topic_id?: number; limit?: number; offset?: number }) =>
    request<InboxListResponse>("/api/v1/inbox", { ...options }),
  getInboxCounts: () => request<InboxCounts>("/api/v1/inbox/counts"),
  setInboxState: (signalIds: number[], state: InboxState, note?: string) =>
    request<{ updated: number }>("/api/v1/inbox/state", undefined, {
      method: "POST",
      body: { signal_ids: signalIds, state, note },
    }),
  getReplyDraft: (signalId: number) =>
    request<ReplyDraft>(`/api/v1/inbox/${signalId}/reply-draft`, undefined, { method: "POST" }),

  // Public
  runDemo: (url: string) =>
    request<DemoResult>("/api/v1/demo", undefined, { method: "POST", body: { url } }),
  getReports: () => request<{ items: ReportSummary[] }>("/api/v1/reports"),
  getReport: (clusterId: string | number) => request<Report>(`/api/v1/reports/${clusterId}`),
  reportMarkdownUrl: (clusterId: string | number) => buildUrl(`/api/v1/reports/${clusterId}.md`).toString(),

  // Onboarding
  analyzeSite: (url: string) =>
    request<Proposal>("/api/v1/onboarding/analyze", undefined, { method: "POST", body: { url } }),
  confirmOnboarding: (input: { website_url?: string; product_summary?: string; topics: ProposalTopic[] }) =>
    request<ConfirmResult>("/api/v1/onboarding/confirm", undefined, { method: "POST", body: input }),
};
