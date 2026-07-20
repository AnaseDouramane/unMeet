export type TrendStatus = "new" | "rising" | "stable" | "falling";
export type TrendPeriod = "day" | "week" | "month";
export type ClusterSort = "document_count" | "opportunity_score" | "growth_rate";

export interface DashboardSummary {
  total_problems: number;
  total_clusters: number;
  new_clusters: number;
  rising_clusters: number;
  stable_clusters: number;
  falling_clusters: number;
  source_count: number;
  latest_run_id: number | null;
  latest_run_created_at: string | null;
}

export interface TrendDistribution {
  new_count: number;
  rising_count: number;
  stable_count: number;
  falling_count: number;
}

export interface SourceBreakdownItem {
  source: string;
  problem_count: number;
  percentage: number;
}

export interface TimeSeriesPoint {
  period_start: string;
  problem_count: number;
  cluster_count: number;
  new_count: number;
  rising_count: number;
  stable_count: number;
  falling_count: number;
}

export interface Opportunity {
  cluster_id: number;
  label: string;
  rank: number;
  opportunity_score: number;
  document_count: number;
  growth_rate: number | null;
  status: TrendStatus;
  source_count: number;
  average_problem_confidence: number;
  keywords: string[];
}

export interface ApiErrorPayload {
  code?: string;
  message?: string;
  details?: unknown;
}

export interface AnalyticsSummaryResponse {
  summary: DashboardSummary;
  trend_distribution: TrendDistribution;
  source_breakdown: SourceBreakdownItem[];
}

export interface OpportunityListResponse {
  items: Opportunity[];
}

export interface ClusterListResponse extends OpportunityListResponse {
  limit: number;
  offset: number;
}

export interface PublicDocument {
  id: number;
  source: string;
  title: string;
  body: string;
  url: string;
  author: string | null;
  published_at: string;
  problem_confidence: number;
  similarity?: number;
}

export interface ClusterDetailResponse {
  cluster: Opportunity;
  documents: PublicDocument[];
}

export interface TrendsResponse {
  trend_distribution: TrendDistribution;
  time_series: TimeSeriesPoint[];
}

export interface SearchResponse {
  items: PublicDocument[];
}
