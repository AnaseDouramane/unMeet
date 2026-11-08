import type { Metadata } from "next";
import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { api, ApiClientError } from "@/lib/api";
import { formatDate, formatGrowthRate } from "@/lib/formatters";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  try {
    const report = await api.getReport(id);
    return {
      title: report.title,
      description: `${report.document_count} public posts describe this problem: ${report.title}.`,
    };
  } catch {
    return { title: "Pain report" };
  }
}

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const report = await api.getReport(id);
    return (
      <article className="max-w-3xl">
        <Link href="/reports" className="text-sm font-medium text-indigo-700 hover:underline">
          ← All reports
        </Link>
        <h1 className="mt-3 text-3xl font-bold tracking-tight">{report.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <StatusBadge status={report.status} />
          <span>
            {report.document_count} public posts · {report.source_count} source{report.source_count === 1 ? "" : "s"} ·{" "}
            {formatGrowthRate(report.growth_rate)}
          </span>
        </div>
        <h2 className="mt-8 text-lg font-semibold">What people are saying</h2>
        <ul className="mt-3 space-y-4">
          {report.quotes.map((quote) => (
            <li key={quote.url}>
              <blockquote className="border-l-2 border-slate-800 pl-4 text-base text-slate-900">“{quote.text}”</blockquote>
              <a href={quote.url} target="_blank" rel="noreferrer" className="mt-1 inline-block pl-4 text-xs text-indigo-700 hover:underline">
                {quote.source}, {formatDate(quote.published_at)}
              </a>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-xs text-slate-500">
          Quotes are public posts, shown as written and linked to their source.{" "}
          <a href={api.reportMarkdownUrl(report.cluster_id)} className="underline">
            Markdown version
          </a>
        </p>
      </article>
    );
  } catch (error) {
    const message = error instanceof ApiClientError && error.status === 404 ? "This report does not exist." : "The report could not be loaded.";
    return (
      <p role="alert" className="text-rose-700">
        {message}
      </p>
    );
  }
}
