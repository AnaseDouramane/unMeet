import type { DashboardSummary } from "@/lib/types";

export function KpiGrid({ summary }: { summary: DashboardSummary }) {
  const cards = [
    ["Total problems", summary.total_problems],
    ["Total clusters", summary.total_clusters],
    ["New clusters", summary.new_clusters],
    ["Rising clusters", summary.rising_clusters],
    ["Sources", summary.source_count],
  ];
  return <section aria-label="Key performance indicators" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">{cards.map(([label, value]) => <article key={String(label)} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-sm text-slate-600">{label}</p><p className="mt-2 text-3xl font-bold text-ink">{value}</p></article>)}</section>;
}
