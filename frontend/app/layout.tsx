import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = { title: "unMeet", description: "Problem intelligence dashboard" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><div className="min-h-screen md:flex"><aside className="border-b border-slate-200 bg-white p-4 md:min-h-screen md:w-56 md:border-b-0 md:border-r"><Link href="/" className="text-xl font-bold text-indigo-700">unMeet</Link><nav aria-label="Main navigation" className="mt-5 flex gap-2 md:flex-col"><Link className="rounded px-3 py-2 text-sm font-medium hover:bg-slate-100" href="/">Dashboard</Link><Link className="rounded px-3 py-2 text-sm font-medium hover:bg-slate-100" href="/clusters">Clusters</Link><Link className="rounded px-3 py-2 text-sm font-medium hover:bg-slate-100" href="/search">Search</Link></nav></aside><main className="min-w-0 flex-1 p-5 md:p-8">{children}</main></div></body></html>;
}
