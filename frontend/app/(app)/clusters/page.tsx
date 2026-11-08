import { ClusterFilters } from "@/components/clusters/cluster-filters";
import { ClusterList } from "@/components/clusters/cluster-list";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState } from "@/components/ui/states";
import { api, ApiClientError } from "@/lib/api";
import type { ClusterSort, TrendStatus } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ClustersPage({ searchParams }: { searchParams: Promise<{ status?: TrendStatus; sort_by?: ClusterSort }> }) {
  const params = await searchParams;
  try {
    const clusters = await api.getClusters({ limit: 50, status: params.status, sort_by: params.sort_by ?? "opportunity_score" });
    return <><PageHeader title="Clusters" description="Explore grouped problem signals and their current trend." /><ClusterFilters /><ClusterList items={clusters.items} /></>;
  } catch (error) {
    const message = error instanceof ApiClientError ? error.message : "Clusters could not be loaded.";
    return <><PageHeader title="Clusters" description="Explore grouped problem signals and their current trend." /><ErrorState message={message} /></>;
  }
}
