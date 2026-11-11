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

export type SignalIntent =
  | "pain_point"
  | "feature_request"
  | "solution_search"
  | "competitor_complaint";

export interface Signal {
  id: number;
  source: string;
  title: string;
  url: string;
  author: string | null;
  published_at: string;
  intent: SignalIntent | "none" | null;
  pain_quote: string | null;
  products_mentioned: string[];
  severity: number | null;
  confidence: number;
  similarity: number | null;
  relevance_reason?: string | null;
}

export interface SignalListResponse {
  items: Signal[];
  limit: number;
  offset: number;
}

export interface SignalFilters {
  topic?: string;
  intent?: SignalIntent[];
  product?: string[];
  source?: string[];
  min_severity?: number;
  since?: string;
  limit?: number;
  offset?: number;
}

export interface Topic {
  id: number;
  name: string;
  description: string | null;
  intents: SignalIntent[];
  products: string[];
  sources: string[];
  keywords?: string[];
  min_severity: number | null;
  max_distance: number;
  has_webhook: boolean;
  created_at: string | null;
  last_delivered_at: string | null;
}

export interface TopicListResponse {
  items: Topic[];
}

export interface TopicInput {
  name: string;
  description?: string;
  intents?: SignalIntent[];
  products?: string[];
  keywords?: string[];
  min_severity?: number;
  webhook_url?: string;
}

export type InboxState = "new" | "relevant" | "not_relevant" | "replied";

export interface InboxItem {
  signal_id: number;
  source: string;
  title: string;
  url: string;
  author: string | null;
  published_at: string;
  intent: SignalIntent | "none" | null;
  pain_quote: string | null;
  products_mentioned: string[];
  severity: number | null;
  topic_id: number;
  topic_name: string;
  relevance_reason: string;
  state: InboxState;
  note: string | null;
  updated_at: string | null;
}

export interface InboxListResponse {
  items: InboxItem[];
  limit: number;
  offset: number;
}

export type InboxCounts = Record<InboxState, number>;

export interface ReplyDraft {
  draft: string;
  mentions_product: boolean;
  disclosure_added: boolean;
  community_rules: string;
  note: string;
}

export interface PlanInfo {
  name: string;
  monthly_price_eur: number;
  max_topics: number;
  max_seats: number;
  llm_budget_usd: number;
  webhooks: boolean;
  daily_digest: boolean;
}

export interface WorkspaceInfo {
  id: number;
  name: string;
  slug: string;
  plan: PlanInfo;
  role: "owner" | "admin" | "member" | null;
  topics_used: number | null;
  seats_used: number | null;
}

export interface Member {
  user_id: number;
  email: string;
  role: "owner" | "admin" | "member";
}

export interface ApiKeyInfo {
  id: number;
  name: string;
  prefix: string;
  created_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKeyInfo {
  key: string;
}

export interface ChannelInfo {
  id: number;
  kind: "email" | "slack";
  target: string;
  frequency: "daily" | "weekly";
  enabled: boolean;
  last_sent_at: string | null;
  last_error: string | null;
}

export interface ChannelInput {
  kind: "email" | "slack";
  target: string;
  frequency: "daily" | "weekly";
}

export interface ProposalTopic {
  name: string;
  description: string;
  intents: string[];
  products: string[];
  keywords?: string[];
}

export interface Proposal {
  source_url: string;
  product_summary: string;
  icp: string;
  competitors: string[];
  topics: ProposalTopic[];
}

export interface ConfirmResult {
  created: Topic[];
  skipped: { name: string; reason: string }[];
}

export interface DemoSignal {
  source: string;
  title: string;
  url: string;
  published_at: string;
  quote: string | null;
  intent: string | null;
  similarity: number | null;
}

export interface DemoResult {
  product_summary: string;
  competitors: string[];
  topics: string[];
  signals: DemoSignal[];
}

export interface ReportSummary {
  cluster_id: number;
  title: string;
  status: TrendStatus;
  growth_rate: number | null;
  document_count: number;
  source_count: number;
}

export interface ReportQuote {
  source: string;
  title: string;
  url: string;
  published_at: string;
  text: string;
}

export interface Report extends ReportSummary {
  quotes: ReportQuote[];
}

export interface OverviewTopic {
  id: number;
  name: string;
  description: string | null;
  keywords: string[];
  products: string[];
  matched: number;
  new: number;
}

export interface OverviewRun {
  source: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  status: "ok" | "error";
  acquired: number;
  skipped: number;
  gated_out: number;
  llm_requests: number;
  problems: number;
  matched: number;
  errors: number;
  error: string | null;
}

export interface Overview {
  workspace: { name: string; plan: string; website_url: string | null; product_summary: string | null };
  inbox: InboxCounts;
  topics: OverviewTopic[];
  runs: OverviewRun[];
  usage: { calls: number; total_tokens: number; spent_usd: number | null; llm_budget_usd: number };
}
