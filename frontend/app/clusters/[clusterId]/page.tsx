import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiClientError } from "@/lib/api";
import { excerpt, formatGrowthRate, formatPercentage } from "@/lib/formatters";

export const dynamic = "force-dynamic";

export default async function ClusterDetailPage({ params }: { params: Promise<{ clusterId: string }> }) {
  const { clusterId } = await params;
  try {
    const detail = await api.getCluster(clusterId);
    const { cluster } = detail;
    return <><PageHeader title={cluster.label} description="Cluster detail and associated problem documents." /><div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-3"><StatusBadge status={cluster.status} /><span className="text-sm font-semibold">Score {formatPercentage(cluster.opportunity_score)}</span></div><div className="mt-4 flex flex-wrap gap-2">{cluster.keywords.map((keyword) => <span key={keyword} className="rounded bg-slate-100 px-2 py-1 text-xs">{keyword}</span>)}</div><dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3"><div><dt className="text-slate-500">Documents</dt><dd className="font-semibold">{cluster.document_count}</dd></div><div><dt className="text-slate-500">Growth</dt><dd className="font-semibold">{formatGrowthRate(cluster.growth_rate)}</dd></div><div><dt className="text-slate-500">Sources</dt><dd className="font-semibold">{cluster.source_count}</dd></div></dl></div><section className="mt-6"><h2 className="mb-3 text-lg font-semibold">Associated documents</h2>{detail.documents.length === 0 ? <EmptyState title="No documents available" message="This cluster has no public documents to display." /> : <div className="grid gap-3">{detail.documents.map((document) => <article key={document.id} className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex justify-between gap-3"><h3 className="font-semibold">{document.title}</h3><span className="text-xs text-slate-500">{document.source}</span></div><p className="mt-2 text-sm text-slate-600">{excerpt(document.body)}</p>{document.url && <a href={document.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm font-medium text-indigo-700 hover:underline">Open original post</a>}</article>)}</div>}</section><Link href="/clusters" className="mt-6 inline-block text-sm font-medium text-indigo-700 hover:underline">← Back to clusters</Link></>;
  } catch (error) {
    const message = error instanceof ApiClientError && error.status === 404 ? "This cluster no longer exists." : error instanceof ApiClientError ? error.message : "Cluster detail could not be loaded.";
    return <><PageHeader title="Cluster" description="Cluster detail and associated problem documents." /><ErrorState message={message} /></>;
  }
}
