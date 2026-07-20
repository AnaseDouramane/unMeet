import type {
  AnalyticsSummaryResponse,
  ClusterDetailResponse,
  ClusterListResponse,
  ClusterSort,
  OpportunityListResponse,
  SearchResponse,
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

function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!baseUrl) {
    throw new ApiClientError(
      "NEXT_PUBLIC_API_BASE_URL is not configured. Copy .env.example to .env.local and set it.",
    );
  }
  return baseUrl.replace(/\/$/, "");
}

async function request<T>(path: string, parameters?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${getApiBaseUrl()}${path}`);
  for (const [key, value] of Object.entries(parameters ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  let response: Response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
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
  return (await response.json()) as T;
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
};
