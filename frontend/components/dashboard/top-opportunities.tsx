import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/states";
import { formatGrowthRate, formatPercentage } from "@/lib/formatters";
import type { Opportunity } from "@/lib/types";

export function TopOpportunities({ items }: { items: Opportunity[] }) {
  if (!items.length) return <EmptyState title="No opportunities yet" message="Run analysis to populate opportunity ranking." />;
  return <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-200 p-4"><h2 className="font-semibold">Top opportunities</h2></div><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-slate-600"><tr><th className="p-3">Rank</th><th className="p-3">Cluster</th><th className="p-3">Score</th><th className="p-3">Documents</th><th className="p-3">Growth</th><th className="p-3">Status</th><th className="p-3">Sources</th></tr></thead><tbody>{items.map((item) => <tr key={item.cluster_id} className="border-t border-slate-100"><td className="p-3 font-semibold">#{item.rank}</td><td className="p-3"><Link className="font-medium text-indigo-700 hover:underline" href={`/clusters/${item.cluster_id}`}>{item.label}</Link></td><td className="p-3">{formatPercentage(item.opportunity_score)}</td><td className="p-3">{item.document_count}</td><td className="p-3">{formatGrowthRate(item.growth_rate)}</td><td className="p-3"><StatusBadge status={item.status} /></td><td className="p-3">{item.source_count}</td></tr>)}</tbody></table></div></section>;
}
