export function PageHeader({ title, description }: { title: string; description: string }) {
  return <header className="mb-7"><h1 className="text-2xl font-bold tracking-tight text-ink">{title}</h1><p className="mt-1 text-sm text-slate-600">{description}</p></header>;
}
