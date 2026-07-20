export function formatPercentage(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

export function formatGrowthRate(value: number | null): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${formatPercentage(value)}`;
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(value));
}

export function excerpt(value: string, maximumLength = 180): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length <= maximumLength ? normalized : `${normalized.slice(0, maximumLength)}…`;
}
