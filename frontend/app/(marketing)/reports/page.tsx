import type { Metadata } from "next";
import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { api, ApiClientError } from "@/lib/api";
import { formatGrowthRate } from "@/lib/formatters";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Pain reports",
  description: "Recurring problems people describe in public communities, how fast they are growing and what they actually say.",
};

export default async function ReportsPage() {
  let reports;
  try {
    reports = (await api.getReports()).items;
  } catch (error) {
    const message = error instanceof ApiClientError ? error.message : "Reports could not be loaded.";
    return (
      <>
        <h1 className="text-2xl font-bold">Pain reports</h1>
        <p role="alert" className="mt-4 text-rose-700">
          {message}
        </p>
      </>
    );
  }
  return (
    <>
      <h1 className="text-2xl font-bold">Pain reports</h1>
      <p className="mt-2 max-w-2xl text-slate-600">
        Recurring problems people describe in public communities. A report appears only when enough independent posts
        support it. Quotes are shown as written and linked to their source.
      </p>
      {reports.length === 0 ? (
        <p className="mt-8 rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">
          No report has enough evidence yet. Check back soon.
        </p>
      ) : (
        <ul className="mt-6 grid gap-4">
          {reports.map((report) => (
            <li key={report.cluster_id}>
              <Link
                href={`/reports/${report.cluster_id}`}
                className="block rounded-xl border border-slate-200 p-5 hover:border-indigo-400"
              >
                <div className="flex items-center justify-between gap-3">
                  <h2 className="font-semibold">{report.title}</h2>
                  <StatusBadge status={report.status} />
                </div>
                <p className="mt-2 text-sm text-slate-600">
                  {report.document_count} posts · {report.source_count} source{report.source_count === 1 ? "" : "s"} ·{" "}
                  {formatGrowthRate(report.growth_rate)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
