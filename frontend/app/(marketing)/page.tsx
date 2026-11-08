import Link from "next/link";

import { DemoForm } from "@/components/marketing/demo-form";
import { PlansTable } from "@/components/marketing/plans-table";

const contact = process.env.NEXT_PUBLIC_CONTACT_EMAIL?.trim();

const STEPS = [
  { title: "Paste your website", text: "We read the public page and work out what you sell, who competes with you and which pains you solve." },
  { title: "We watch public conversations", text: "Hacker News, Reddit, Stack Exchange and GitHub, all day. We match meaning, not keywords, and keep only people with real intent." },
  { title: "You get a short inbox", text: "Each item has the author's exact words, why it matches and a reply draft that discloses who you are. You post it yourself." },
];

export default function LandingPage() {
  return (
    <div className="space-y-16">
      <section className="max-w-3xl">
        <h1 className="text-4xl font-bold tracking-tight text-slate-900">Find the people asking for a tool like yours, today.</h1>
        <p className="mt-4 text-lg text-slate-600">
          unMeet reads public conversations and sends you the ones where someone is looking for what you sell or complaining about
          a competitor. One URL to set up, no keyword lists.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          {contact ? (
            <a href={`mailto:${contact}?subject=unMeet%20access`} className="rounded bg-indigo-700 px-5 py-3 font-semibold text-white">
              Request access
            </a>
          ) : (
            <Link href="/onboarding" className="rounded bg-indigo-700 px-5 py-3 font-semibold text-white">
              Get started
            </Link>
          )}
          <Link href="/reports" className="rounded px-5 py-3 font-semibold text-slate-700 ring-1 ring-slate-300">
            Read the pain reports
          </Link>
        </div>
      </section>

      <section aria-labelledby="demo-title" className="rounded-2xl bg-slate-50 p-6">
        <h2 id="demo-title" className="text-xl font-semibold">
          Try it on your site
        </h2>
        <p className="mb-4 mt-1 text-sm text-slate-600">Real, recent public conversations that match your product. No sign-up.</p>
        <DemoForm />
      </section>

      <section aria-labelledby="how-title">
        <h2 id="how-title" className="text-xl font-semibold">
          How it works
        </h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="rounded-xl border border-slate-200 p-5">
              <span className="text-sm font-semibold text-indigo-700">Step {index + 1}</span>
              <h3 className="mt-1 font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="why-title">
        <h2 id="why-title" className="text-xl font-semibold">
          Why not just set up keyword alerts?
        </h2>
        <ul className="mt-4 grid gap-4 text-sm text-slate-700 sm:grid-cols-2">
          <li className="rounded-xl border border-slate-200 p-4">
            <strong>Meaning, not words.</strong> &ldquo;Anything that fixes duplicate contacts?&rdquo; matches even though it never says your
            product&apos;s name.
          </li>
          <li className="rounded-xl border border-slate-200 p-4">
            <strong>Verified quotes.</strong> Every quote is checked against the original post; anything the model paraphrased is dropped.
          </li>
          <li className="rounded-xl border border-slate-200 p-4">
            <strong>It learns from you.</strong> Mark a conversation relevant or not and the next matches follow your judgement.
          </li>
          <li className="rounded-xl border border-slate-200 p-4">
            <strong>Respectful by design.</strong> Drafts disclose your affiliation, follow each community&apos;s rules and are never posted
            for you.
          </li>
        </ul>
      </section>

      <section id="pricing" aria-labelledby="pricing-title">
        <h2 id="pricing-title" className="text-xl font-semibold">
          Pricing
        </h2>
        <p className="mb-4 mt-1 text-sm text-slate-600">Early-access prices; we are onboarding design partners by hand.</p>
        <PlansTable />
      </section>
    </div>
  );
}
