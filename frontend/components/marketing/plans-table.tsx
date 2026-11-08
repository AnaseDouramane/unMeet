"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { FALLBACK_PLANS } from "@/lib/plans";
import type { PlanInfo } from "@/lib/types";

export function PlansTable() {
  const [plans, setPlans] = useState<PlanInfo[]>(FALLBACK_PLANS);

  useEffect(() => {
    api
      .getPlans()
      .then((live) => live.length > 0 && setPlans(live))
      .catch(() => undefined);
  }, []);

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {plans.map((plan) => (
        <article key={plan.name} className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="text-lg font-semibold capitalize">{plan.name}</h3>
          <p className="mt-1 text-3xl font-bold">
            {plan.monthly_price_eur === 0 ? "Free" : `€${plan.monthly_price_eur}`}
            {plan.monthly_price_eur > 0 && <span className="text-sm font-normal text-slate-500"> /month</span>}
          </p>
          <ul className="mt-4 space-y-1 text-sm text-slate-700">
            <li>{plan.max_topics} topic{plan.max_topics === 1 ? "" : "s"}</li>
            <li>{plan.max_seats} seat{plan.max_seats === 1 ? "" : "s"}</li>
            <li>{plan.daily_digest ? "Daily email digest" : "Weekly email digest"}</li>
            <li>{plan.webhooks ? "Slack and webhooks" : "No Slack or webhooks"}</li>
            <li>Reply drafts and CSV export</li>
          </ul>
        </article>
      ))}
    </div>
  );
}
