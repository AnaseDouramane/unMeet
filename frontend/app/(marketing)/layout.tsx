import Link from "next/link";

const contact = process.env.NEXT_PUBLIC_CONTACT_EMAIL?.trim();

export default function MarketingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <Link href="/" className="text-xl font-bold text-indigo-700">
            unMeet
          </Link>
          <nav aria-label="Site" className="flex items-center gap-5 text-sm font-medium text-slate-700">
            <Link href="/#pricing" className="hover:text-indigo-700">
              Pricing
            </Link>
            <Link href="/reports" className="hover:text-indigo-700">
              Pain reports
            </Link>
            <Link href="/inbox" className="rounded bg-indigo-700 px-3 py-2 text-white">
              Open app
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-10">{children}</main>
      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500">
        <Link href="/privacy" className="underline">
          Privacy
        </Link>
        {contact ? (
          <>
            {" · "}
            <a href={`mailto:${contact}`} className="underline">
              Contact
            </a>
          </>
        ) : null}
      </footer>
    </div>
  );
}
