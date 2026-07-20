import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/states";
import { formatGrowthRate, formatPercentage } from "@/lib/formatters";
import type { Opportunity } from "@/lib/types";

export function ClusterList({ items }: { items: Opportunity[] }) {
  if (!items.length) return <EmptyState title="No matching clusters" message="Try changing the current filters." />;
  return <div className="grid gap-4">{items.map((cluster) => <article key={cluster.cluster_id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><Link href={`/clusters/${cluster.cluster_id}`} className="text-lg font-semibold text-indigo-700 hover:underline">{cluster.label}</Link><div className="mt-2 flex flex-wrap gap-2">{cluster.keywords.map((keyword) => <span key={keyword} className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">{keyword}</span>)}</div></div><StatusBadge status={cluster.status} /></div><dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4"><div><dt className="text-slate-500">Documents</dt><dd className="font-semibold">{cluster.document_count}</dd></div><div><dt className="text-slate-500">Growth</dt><dd className="font-semibold">{formatGrowthRate(cluster.growth_rate)}</dd></div><div><dt className="text-slate-500">Score</dt><dd className="font-semibold">{formatPercentage(cluster.opportunity_score)}</dd></div><div><dt className="text-slate-500">Sources</dt><dd className="font-semibold">{cluster.source_count}</dd></div></dl></article>)}</div>;
}
