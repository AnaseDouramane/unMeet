"use client";

import { useRouter, useSearchParams } from "next/navigation";

import type { ClusterSort, TrendStatus } from "@/lib/types";

export function ClusterFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();
  function update(name: "status" | "sort_by", value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(name, value); else params.delete(name);
    params.delete("offset");
    router.push(`/clusters?${params.toString()}`);
  }
  return <div className="mb-5 flex flex-col gap-3 sm:flex-row"><label className="text-sm font-medium">Status<select aria-label="Filter by status" value={searchParams.get("status") ?? ""} onChange={(event) => update("status", event.target.value)} className="ml-2 rounded border border-slate-300 bg-white p-2"><option value="">All</option>{(["new", "rising", "stable", "falling"] as TrendStatus[]).map((status) => <option key={status} value={status}>{status}</option>)}</select></label><label className="text-sm font-medium">Sort by<select aria-label="Sort clusters" value={searchParams.get("sort_by") ?? "opportunity_score"} onChange={(event) => update("sort_by", event.target.value)} className="ml-2 rounded border border-slate-300 bg-white p-2">{(["opportunity_score", "document_count", "growth_rate"] as ClusterSort[]).map((sort) => <option key={sort} value={sort}>{sort.replace("_", " ")}</option>)}</select></label></div>;
}
