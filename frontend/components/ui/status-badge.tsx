import type { TrendStatus } from "@/lib/types";

const styles: Record<TrendStatus, string> = {
  new: "bg-violet-100 text-violet-800",
  rising: "bg-emerald-100 text-emerald-800",
  stable: "bg-slate-100 text-slate-700",
  falling: "bg-rose-100 text-rose-800",
};

export function StatusBadge({ status }: { status: TrendStatus }) {
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${styles[status]}`}>{status}</span>;
}
