# unMeet — plan for the next phase

Hand this file to Claude Code. It is the source of truth for what to build next and why.
Breaking changes to the original design are allowed when they serve the goals below.

## 1. Where we are (`main`, November 2026)

The milestones M1–M4 are implemented and merged; M0 (the live validation) is only started. Numbers
below were measured, not estimated.

| Milestone | Status | Notes |
|-----------|--------|-------|
| M0.1 merge the revamp | done | |
| M0.2 first live run | **started** | small runs with Groq (`openai/gpt-oss-120b`) on Hacker News only; no Reddit credentials yet |
| M0.3 labelled evaluation set | **not started** | needs ~300 human labels; precision/recall/F1 with CI are still unknown |
| M1.1 topic gate before the LLM | done | live: 34 of 75 posts dropped before the model |
| M1.2 batched, topic-aware matching with a reason | done | live: 13 LLM requests for 41 posts |
| M1.3 hosted embeddings | **not done** | costs money; MiniLM still runs locally (torch stays in the image) |
| M1.4 polling worker with cursors | done | |
| M1.5 new sources | partly | Hacker News search and Stack Exchange work live; Bluesky, GitHub Discussions, Product Hunt not built |
| M2 multi-tenant SaaS | done except billing/CRM/login UI | workspaces, roles, API keys, JWT verification, inbox, onboarding, reply drafts, digests, plan limits. Not built: Stripe, HubSpot/Pipedrive push, provider sign-in button |
| M3 launch surface | done | landing + demo (off by default), public reports, dogfood seed, `docs/LAUNCH.md`. Launch actions are the owner's |
| M4 hardening | done except deploy | rate limits, audit, JSON logs, LLM cost tracking, GDPR tooling; Dockerfile written but never built; nothing deployed |

Quality: 704 backend tests (including PostgreSQL integration), 52 frontend tests, ruff, `python -m mypy
app` (the plain `mypy` command can miss imports) and the frontend lint/build are clean in CI.

What the live runs showed (small samples, treat as directions, not results):

- The pipeline works end to end on real data with 0 classification errors; a generic classification
  costs about 1,100 tokens per post with a reasoning model.
- Hacker News is a thin source for GTM buyer intent. Algolia's default fuzzy search returned mostly
  unrelated comments; exact phrases fixed that. With the dogfood topics, 75 posts produced 3 inbox
  matches: one clearly right, one plausible, one wrong. Reddit is where this intent mostly lives, so
  M0.2 needs Reddit OAuth.
- The topic gate threshold (`max_distance` 0.6) is strict on MiniLM distances (best matches 0.54–0.9).
  Do not change it without labelled positives (M0.3).

Next, in this order: Reddit OAuth + the first labelled set (M0.2/M0.3), then tune the gate threshold and
prompts against it, then billing and deploy. The discovery track (M5) should wait until the GTM core
is validated.

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

### M5 — Discovery mode: find unmet consumer demand (separate track)

Goal: reuse the same engine to answer "what are people asking for that no product serves
well?" — starting with consumer apps. This is a second mode of the engine, not a fork: it must
not change the behaviour of GTM workspaces.

1. **Discovery profile, selected by configuration.**
   - A `DISCOVERY` profile (or a workspace flag) that bypasses the topic gate and instead
     keeps only items with intent `solution_search` or `feature_request`, using a cheap
     pre-filter first (phrases such as "is there an app", "I wish there was", "why can't my
     iPhone", "app idea", "someone should make", "looking for an app") before any LLM call.
   - Consumer sources via config: r/iphone, r/apple, r/ios, r/androidapps, r/AppIdeas,
     r/SomebodyMakeThis, r/productivity, r/ADHD, r/personalfinance, r/travel, Ask HN.
     Re-check each subreddit's rules and the Reddit Data API terms for this use.
2. **Consumer variant of the classifier prompt.** Today `SYSTEM_PROMPT` in
   `app/problem_detection/llm.py` is written for go-to-market teams. Add a consumer variant
   selected by the profile, which also extracts: `requested_capability` (one sentence, what
   the person wants to be able to do), `platform` (ios / android / web / desktop / any) and
   `workaround` (what they do today, verbatim when present). Keep the verbatim-quote rule and
   strict validation; add a migration for the new fields.
3. **Coverage check ("does it already exist?").** `app/market` was removed; build it again as
   `app/coverage` with a provider interface:
   - App Store via the public iTunes Search API (`/search?entity=software`): name, rating,
     rating count, last update, price.
   - Google Play (only through an allowed API or a licensed data provider; no scraping).
   - Product Hunt API and GitHub search for existing tools/repos.
   For each cluster, generate 3–5 search queries from its `requested_capability` statements,
   collect candidates, and let the LLM judge whether each candidate actually provides the
   capability (with a one-line reason). Classify the cluster as:
   - `unserved`: no matching product;
   - `poorly_served`: matches exist but are weak (for example rating < 4.0, < 100 ratings,
     not updated for 12+ months, or platform missing);
   - `served`: a strong product exists (store the evidence).
   Cache results per query with a TTL; record cost in the usage tracker.
4. **Opportunity score for discovery clusters:** demand (distinct authors, growth across runs),
   urgency (severity, workaround pain), coverage gap (`unserved` > `poorly_served` > `served`),
   platform fit. Make the weights explicit and test them.
5. **Output:** an "Opportunities" view and `GET /api/v1/discovery/opportunities` listing each
   cluster with its problem statement, 3 verbatim quotes with links, request count and trend,
   coverage verdict with the competitors found and why they fall short. Add a CSV export.
6. **Evaluation:** label 100 clusters by hand as served / poorly served / unserved; report
   agreement of the coverage check with intervals. A false "unserved" costs weeks of building
   the wrong thing, so optimise precision on `unserved`.
7. **Dogfooding deliverable:** run discovery for two weeks on consumer sources and produce a
   short report of the top 10 opportunities with evidence. This feeds the choice of a B2C side
   project and is a portfolio story in itself.

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
