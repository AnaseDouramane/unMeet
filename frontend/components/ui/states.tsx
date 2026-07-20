"use client";

export function EmptyState({ title, message }: { title: string; message: string }) {
  return <section className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center"><h2 className="font-semibold">{title}</h2><p className="mt-2 text-sm text-slate-600">{message}</p></section>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <section role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-rose-900"><h2 className="font-semibold">Unable to load data</h2><p className="mt-1 text-sm">{message}</p>{onRetry && <button type="button" onClick={onRetry} className="mt-4 rounded bg-rose-800 px-3 py-2 text-sm font-semibold text-white">Retry</button>}</section>;
}

export function LoadingSkeleton() {
  return <div aria-label="Loading" className="animate-pulse space-y-4"><div className="h-24 rounded-xl bg-slate-200" /><div className="h-64 rounded-xl bg-slate-200" /></div>;
}
