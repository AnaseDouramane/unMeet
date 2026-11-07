import { formatDate, formatPercentage } from "@/lib/formatters";
import type { Signal } from "@/lib/types";

const intentLabels: Record<string, string> = {
  pain_point: "Pain point",
  feature_request: "Feature request",
  solution_search: "Looking for a solution",
  competitor_complaint: "Competitor complaint",
};

const intentStyles: Record<string, string> = {
  pain_point: "bg-slate-100 text-slate-800",
  feature_request: "bg-sky-100 text-sky-800",
  solution_search: "bg-emerald-100 text-emerald-800",
  competitor_complaint: "bg-amber-100 text-amber-900",
};

export function IntentBadge({ intent }: { intent: Signal["intent"] }) {
  if (!intent || intent === "none") return null;
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${intentStyles[intent]}`}>
      {intentLabels[intent]}
    </span>
  );
}

export function SeverityMeter({ severity }: { severity: number | null }) {
  if (!severity) return null;
  return (
    <span className="flex items-center gap-1 text-xs text-slate-500" title={`Severity ${severity} of 3`}>
      <span className="sr-only">Severity {severity} of 3</span>
      {[1, 2, 3].map((level) => (
        <span
          key={level}
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${level <= severity ? "bg-slate-800" : "bg-slate-200"}`}
        />
      ))}
    </span>
  );
}

export function SignalCard({ signal }: { signal: Signal }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <IntentBadge intent={signal.intent} />
        <SeverityMeter severity={signal.severity} />
        {signal.products_mentioned.map((product) => (
          <span key={product} className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-700">
            {product}
          </span>
        ))}
        {signal.similarity !== null && (
          <span className="ml-auto text-xs text-slate-500">{formatPercentage(signal.similarity)} match</span>
        )}
      </div>
      {signal.pain_quote ? (
        <blockquote className="mt-3 border-l-2 border-slate-800 pl-3 text-base text-slate-900">
          “{signal.pain_quote}”
        </blockquote>
      ) : (
        <p className="mt-3 text-base text-slate-900">{signal.title}</p>
      )}
      {signal.relevance_reason ? (
        <p className="mt-2 text-sm text-slate-600">
          <span className="font-medium text-slate-700">Why it matches:</span> {signal.relevance_reason}
        </p>
      ) : null}
      <footer className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        <span>{signal.author ?? "anonymous"}</span>
        <span>{signal.source}</span>
        <span>{formatDate(signal.published_at)}</span>
        <a className="font-medium text-indigo-700 hover:underline" href={signal.url} target="_blank" rel="noreferrer">
          Open original
        </a>
      </footer>
    </article>
  );
}
