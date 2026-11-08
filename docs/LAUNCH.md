# Launch plan (M3)

Everything below that posts, pays or publishes is **your** action. The product side is built; this is
what to do, in order, and what to say.

## 0. Before anything public (blockers)

- [ ] Real data: run the first live ingestion (M0.2) and look at 50 signals by eye. Do not launch on an empty or
      noisy inbox. Freeze a labelled set and publish precision with its interval (M0.3).
- [ ] Deploy staging, then production (`docs/DEPLOY.md`). Set `UNMEET_API_KEY`, auth variables, `LOG_FORMAT=json`.
- [ ] Reddit: confirm the current Data API terms allow your commercial use, and get OAuth credentials.
- [ ] Legal basics: controller identity and contact on `/privacy`, DPAs with providers (`docs/GDPR.md` checklist).
- [ ] Decide the live demo: set `DEMO_ENABLED=true` only with `DEMO_DAILY_LIMIT` you accept to pay for
      (one LLM analysis per uncached site) and add a bot check (Cloudflare Turnstile) before heavy traffic.
- [ ] Billing: connect a payment provider to `POST /api/v1/workspaces/{id}/plan`, test mode first.
- [ ] Dogfood running: `python -m scripts.seed_dogfood you@company.com --new-key`, then watch the inbox for a week.

## 1. Dogfood: our first customers come from the product

The `unMeet (dogfood)` workspace tracks people asking for lead monitoring, unhappy with keyword alerts, searching
Reddit by hand, or hunting cheaper intent data. Triage the inbox daily, mark relevant / not relevant (this trains
the matching), and reply by hand using the draft, **disclosing who you are**. Follow each community's rules: many
subreddits and Hacker News punish promotion. Help first, mention unMeet only when it truly answers the question.

## 2. Pain reports (content)

`/reports` publishes recurring problems with enough evidence (`REPORT_MIN_DOCUMENTS`, default 5). Each has a Markdown
export (`/api/v1/reports/{id}.md`) for a newsletter, LinkedIn or a blog. One report a week, plus the comment that
explains what you found, is more useful than ten generic posts.

## 3. Launch posts (drafts to edit; do not copy blindly)

**Show HN** (title): `Show HN: unMeet – find people asking for a tool like yours on Reddit and HN`

> I built unMeet because I kept searching Reddit and Hacker News by hand for people who needed what we sell.
> Keyword alerts match words; this matches meaning: you paste your URL, it works out what you sell and who competes
> with you, and shows the conversations where someone is asking for it or complaining about a competitor, with the
> author's exact words (checked against the source) and why it matched. It also drafts a reply that discloses who
> you are; it never posts anything. Try it on your site: <demo link>. I'd love to hear where the matches are wrong.

Rules: answer every comment, be upfront about limitations (sources covered, precision numbers), no upvote requests.

**Product Hunt** tagline (60 chars): `Find buyers asking for your product, right now`
First comment: the problem, the one-URL setup, the verified-quote guarantee, the disclosure-first reply drafts.

**r/SaaS** (check the sub's current self-promotion rules first; if links are not allowed, share the lesson, not the
product): "I analysed N public posts to see what B2B founders complain about when doing outbound. Here is the pattern."
Link the matching pain report only if the rules allow it.

## 4. Twenty founder interviews

Find them with the product itself. Ask for 20 minutes about how they find customers today, not for a sale.

1. Walk me through the last time you found a customer in a public conversation. What did you search?
2. What do you do with a lead you find (CRM, spreadsheet, reply right away)? How long does it take?
3. Which tools do you use for this today and what do you dislike about them?
4. Show them 10 signals from their own URL: which are useful, which are noise, what is missing?
5. Price: at what monthly price would this be too cheap to trust, a bargain, expensive, too expensive?
6. What would you need to see in the first week to keep paying?

Write down exact words. Log each interview with: role, company size, current tool, best/worst signal, price band.

## 5. What to measure

| Metric | Target | Source |
|--------|--------|--------|
| Precision of delivered signals | ≥ 0.8 with interval | frozen eval set, workspace feedback |
| Time to first relevant signals | < 5 min | onboarding wizard |
| AI cost per workspace | < 20% of plan price | `/api/v1/workspace/usage`, `scripts.llm_cost_report` |
| Design partners paying | 10, then €1k MRR | billing |
| Reply acceptance (relevant + replied share) | rising week over week | inbox states |

## 6. Honest limits to state publicly

Sources today: Hacker News, Reddit, Stack Exchange, GitHub. Matching quality depends on the model and the topics; show the
precision number once measured. unMeet does not post for you and does not scrape sites whose terms forbid it.
