# unMeet — plan for the next phase

Hand this file to Claude Code. It is the source of truth for what to build next and why.
Breaking changes to the original design are allowed when they serve the goals below.

## 1. Where we are (branch `revamp/product-ready`)

- Pipeline: HN (stories + comments), Reddit (OAuth), GitHub → clean/dedupe → LLM signal
  extraction (intent, verbatim quote, products, severity) → MiniLM embeddings → Postgres +
  pgvector → UMAP + HDBSCAN clusters with LLM problem statements → trends.
- Product surface: `/api/v1/signals` (+ CSV), tracked topics behind an API key, webhook alerts
  (SSRF-safe), Next.js pages Signals and Topics.
- Quality: 399 backend tests (incl. Postgres integration), 14 frontend tests, ruff + mypy clean,
  Alembic, CI. See `docs/AUDIT.md`.
- **Never run against live sources yet.** The first live run is the first task.

## 2. The pivot: from "problem research" to "buyers asking for you, right now"

Clustering pain points is interesting; finding people who are **asking for a tool like yours or
complaining about your competitor today** is what companies pay for, because it is pipeline.

**Product:** a B2B SaaS founder or GTM lead pastes their website URL. unMeet infers what they
sell, their competitors and the pains they solve, creates topics automatically, and every day
delivers a short inbox of high-intent conversations (Reddit, HN, Bluesky, GitHub, Stack
Exchange) with the exact quote, why it matches, and a suggested reply — pushed to Slack, email,
Clay or the CRM.

**Ideal customer:** seed–Series A B2B SaaS teams without a big outbound team; agencies running
outbound for several clients (multi-workspace).

**Why we can win:** keyword alert tools (F5Bot, Syften, Octolens-style monitors) match words,
not intent; enterprise community tools (Common Room) are expensive and slow to set up. unMeet
matches meaning, verifies quotes, scores intent and needs one URL to set up.

**Pricing to test:** free tier (1 topic, weekly digest) → ~€49/mo (5 topics, daily, Slack/CSV) →
~€149/mo (25 topics, webhooks/CRM, reply drafts, multiple seats). First goal: 10 paying design
partners, then €1k MRR.

**Clusters and trends stay**, repositioned as a "market map" view: what pains in your category are
rising. Good for content marketing and upsell, not the core loop.

## 3. Principles for every change

- Keep the guarantees already in place: verbatim quotes only, idempotent ingestion, strict LLM
  output validation, SSRF-safe webhooks, migrations for every schema change.
- Cost-aware by design: cheap filters first, LLM only on candidates. Track LLM cost per
  workspace.
- Small atomic commits, tests with every change, `ruff check . && mypy app && pytest` green,
  frontend `lint/test/build` green. Never push to `main` directly: work on branches, open PRs.
- Ask before anything that costs money or touches production (new paid APIs, deployments,
  DNS, Stripe live mode).
- No scraping of sites whose terms forbid it (LinkedIn, G2/Capterra pages, X without the paid
  API). Verify the current Reddit Data API terms for commercial use before charging customers.

## 4. Milestones

### M0 — Make it real (first)
1. Merge `revamp/product-ready` into `main` via PR after CI passes.
2. First live run with Groq + Reddit OAuth on ~10 GTM subreddits + Ask HN; fix whatever breaks.
   Log per-stage counts, latency and LLM tokens.
3. Labeled evaluation set: export 300 real items (`scripts.export_eval_sample`), label, freeze.
   Report precision/recall/F1 with CI for `qwen3` vs `llm` (`docs/EVALUATION.md`). Add a 50-item
   golden subset that runs in CI against a recorded-response fixture.

### M1 — Topic-first ingestion (core architecture change)
1. Invert the pipeline: for each new item, embed first (cheap), compute similarity to **all
   active topics**, and send to the LLM only items above a per-topic threshold or matching a
   product/keyword. Expect a large drop in LLM calls; measure it.
2. LLM call becomes "does this item match topic X, with what intent, quote, why" (relevance
   reason shown to the user), batched several items per call where the provider allows.
3. Replace local MiniLM in production with a hosted embedding API behind the same interface
   (keep MiniLM for offline/dev). Remove torch/transformers from the production image.
4. Near real-time: a worker that polls sources every 10–15 minutes with per-source cursors
   (HN Algolia search API for keyword/recent queries; Reddit `new` listings per subreddit).
5. New sources behind the existing connector interface: Bluesky (public firehose/search),
   Stack Exchange (connector exists), GitHub Discussions, Product Hunt comments if the API allows.

### M2 — Multi-tenant SaaS
1. Workspaces, users, roles; auth with Supabase Auth or Clerk. Every topic, signal state and
   delivery belongs to a workspace; row-level isolation tested.
2. Onboarding from a URL: fetch the site, LLM proposes product summary, ICP, competitors, 3–5
   topics; user edits and confirms. Target: first relevant signals in under 5 minutes.
3. Signal inbox: states new / relevant / not relevant / replied; bulk actions; keyboard
   shortcuts. Feedback is stored and used as per-workspace few-shot examples and as eval data.
4. Reply assistant: draft a helpful, non-promotional reply that discloses affiliation, respects
   the community's self-promotion rules and never auto-posts. The user copies and posts.
5. Deliveries: daily email digest, Slack app, webhooks (exists), HubSpot/Pipedrive push, CSV.
6. Stripe billing with plan limits (topics, sources, seats, monthly LLM budget); usage metering.

### M3 — Launch and growth
1. Landing page with a live demo: enter a URL, see 5 real recent signals (rate-limited, cached).
2. Dogfood: an unMeet workspace tracking "people looking for Reddit/HN lead monitoring" —
   our own first customers come from the product.
3. Public "pain reports" per category generated from clusters (SEO, LinkedIn, newsletters).
4. Launch: Show HN, Product Hunt, r/SaaS; 20 founder interviews; iterate pricing.

### M4 — Production hardening (in parallel with M2)
1. Deploy: frontend on Vercel; API + worker on a container host (Fly.io/Railway/Render);
   Postgres with pgvector on Supabase; secrets in the platform; staging and production.
2. Observability: structured logs, error tracking, LLM traces with cost per call/workspace,
   alert on ingestion stalls.
3. GDPR (we are in the EU and store usernames and posts): privacy policy, retention window,
   deletion on request, data processing records, store only what the product needs.
4. Rate limiting on the public API, API keys per workspace (replace the single global key),
   audit log for writes.

## 5. Remove or demote
- Streamlit placeholder dashboard: delete.
- `app/market` experimental connectors: delete unless M3 needs them.
- Qwen3 local classifier: keep for offline experiments only, not in production paths.
- Opportunity ranking UI: move under "Market map".

## 6. Definition of done for this phase
- A stranger can sign up, paste a URL, get relevant signals the same day, and pay.
- Precision of delivered signals ≥ 0.8 on the frozen eval set, measured with CI, reported with
  intervals.
- LLM cost per active workspace per month known and below 20% of the plan price.
- 10 paying design partners.
