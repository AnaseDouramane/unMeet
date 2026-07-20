import { DashboardCharts } from "@/components/charts/dashboard-charts";
import { KpiGrid } from "@/components/dashboard/kpi-grid";
import { TopOpportunities } from "@/components/dashboard/top-opportunities";
import { ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiClientError } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  try {
    const [analytics, opportunities, trends] = await Promise.all([
      api.getSummary(), api.getOpportunities(8), api.getTrends("day", 30),
    ]);
    return <><PageHeader title="Dashboard" description="Signals and ranked problems collected from public communities." /><KpiGrid summary={analytics.summary} /><div className="mt-6"><TopOpportunities items={opportunities.items} /></div><div className="mt-6"><DashboardCharts opportunities={opportunities.items} timeSeries={trends.time_series} distribution={trends.trend_distribution} sources={analytics.source_breakdown} /></div></>;
  } catch (error) {
    const message = error instanceof ApiClientError ? error.message : "Dashboard data could not be loaded.";
    return <><PageHeader title="Dashboard" description="Signals and ranked problems collected from public communities." /><ErrorState message={message} /></>;
  }
}
