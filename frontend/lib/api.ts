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
} from "@/lib/types";

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
  method?: "GET" | "POST" | "DELETE";
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
  if (options.apiKey) headers.Authorization = `Bearer ${options.apiKey}`;
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
};
