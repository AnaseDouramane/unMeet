import type { PlanInfo } from "@/lib/types";

// Mirrors app/billing/plans.py. The landing page shows these when the API is not reachable, and
// uses the live values from GET /api/v1/plans otherwise, so the two cannot drift for long.
export const FALLBACK_PLANS: PlanInfo[] = [
  { name: "free", monthly_price_eur: 0, max_topics: 1, max_seats: 1, llm_budget_usd: 1, webhooks: false, daily_digest: false },
  { name: "starter", monthly_price_eur: 49, max_topics: 5, max_seats: 3, llm_budget_usd: 9, webhooks: false, daily_digest: true },
  { name: "team", monthly_price_eur: 149, max_topics: 25, max_seats: 10, llm_budget_usd: 29, webhooks: true, daily_digest: true },
];
