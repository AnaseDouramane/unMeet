import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy notice · unMeet" };

const controller = process.env.NEXT_PUBLIC_CONTROLLER_NAME?.trim();
const contact = process.env.NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL?.trim();
const nonSignalDays = process.env.NEXT_PUBLIC_RETENTION_NON_SIGNAL_DAYS?.trim() || "30";
const signalDays = process.env.NEXT_PUBLIC_RETENTION_SIGNAL_DAYS?.trim() || "365";

export default function PrivacyPage() {
  const configured = Boolean(controller && contact);
  return (
    <article className="prose max-w-3xl space-y-6 text-slate-800">
      <h1 className="text-2xl font-bold">Privacy notice</h1>

      {!configured && (
        <p role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Controller details are not configured. Set NEXT_PUBLIC_CONTROLLER_NAME and
          NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL before publishing this page.
        </p>
      )}

      <section>
        <h2 className="text-lg font-semibold">Who is responsible</h2>
        <p>
          {controller || "[controller not configured]"} is the controller of the processing
          described here. Contact for privacy requests:{" "}
          {contact ? <a className="text-indigo-700 underline" href={`mailto:${contact}`}>{contact}</a> : "[contact not configured]"}.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">What unMeet does with personal data</h2>
        <p>
          unMeet reads <strong>public</strong> posts and comments on Hacker News, Reddit, GitHub, Stack Exchange
          and similar sources, and detects where people describe a problem or ask for a tool. For each
          item we store the public text, its link, the author&apos;s public username, the publication time
          and the result of the analysis (intent, a short quote, products mentioned, severity). We do not
          collect private messages, email addresses, or anything behind a login, and unMeet never posts
          or messages anyone on your behalf.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Why and on what basis</h2>
        <p>
          Our customers use these public conversations to find people who are asking for help with a
          problem they solve. The basis is legitimate interest (GDPR art. 6(1)(f)): the data is public,
          the use is limited to that purpose, and you can object or ask for deletion at any time.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">How long we keep it</h2>
        <p>
          Posts that turn out not to be relevant are deleted after {nonSignalDays} days. Posts kept as
          signals are deleted after {signalDays} days. Deleting a post at its source does not
          automatically remove our copy, so use the request below if you want it removed sooner.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Who receives it</h2>
        <p>
          Text may be sent to an AI model provider to analyse it, and is stored with our hosting and
          database providers acting as processors. Customers see the public text, link and username of the
          conversations that match their topics.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Your rights</h2>
        <p>
          You can ask for access, correction, deletion or restriction, and object to the processing, by
          writing to the contact above with your username and the site it is from. On a deletion request
          we delete everything we hold about that username and keep only a one-way hash of it so the
          account is not collected again. You can also complain to your data protection authority.
        </p>
      </section>
    </article>
  );
}
