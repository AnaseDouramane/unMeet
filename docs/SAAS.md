# Multi-tenant SaaS: how it works

## Accounts and roles

- A **workspace** owns topics, API keys, members, delivery channels, the inbox state and a plan.
- A **user** belongs to one or more workspaces as `owner`, `admin` or `member`. Owners and admins
  manage members, keys, topics and deliveries; members use the inbox (triage, reply drafts).
- The last owner of a workspace cannot leave; only an owner can add another owner.

## Authentication

Credentials are tried in this order (`app/api/principal.py`):

| Credential | Who | Workspace |
|------------|-----|-----------|
| `um_…` workspace API key | integrations (Clay, scripts) | the key's own workspace (a header cannot change it) |
| `UNMEET_API_KEY` operator key | you / support | `X-Workspace-ID`, default workspace if absent |
| JWT from your auth provider | people | `X-Workspace-ID`, or the user's only workspace |
| none, `UNMEET_ENV=development` | local checkout | the default workspace |

Any other case is `401`. unMeet stores **no passwords**. For login configure one key source:
`AUTH_JWT_SECRET` (HS256, e.g. Supabase's JWT secret) **or** `AUTH_JWKS_URL` (RS256/ES256, e.g.
Clerk, Auth0, newer Supabase projects), plus `AUTH_JWT_ISSUER` and `AUTH_JWT_AUDIENCE`. The token
must carry `sub` and `email`; signature, issuer, audience and expiry are checked and the `none`
algorithm is refused. People are matched by email, so inviting `mia@acme.com` before she signs up
works: the account is linked at her first login.

The frontend currently connects with a workspace API key pasted in the app (kept in
`sessionStorage`, i.e. for the tab). A sign-in button for the chosen provider is a small follow-up
once the provider exists.

## Isolation guarantees (tested)

- Topics, API keys, members, delivery channels and inbox states are always queried with the caller's
  workspace id. A resource of another workspace answers exactly like a missing one (`404`).
- The signal **inbox** only contains signals the model matched to the workspace's own topics, so state
  changes and reply drafts cannot be used to probe the rest of the corpus.
- The public corpus itself (`source_items`) is shared: it is public data, filtered per workspace by
  topic matches. `/signals` requires a workspace credential so the dataset cannot be scraped anonymously.
- `tests/integration/test_tenancy.py`, `test_topics.py`, `test_inbox.py` and `tests/test_tenancy_api.py`
  run these rules against PostgreSQL and the HTTP API.

## Plans and limits

`app/billing/plans.py` (prices to be validated with design partners):

| Plan | € / month | Topics | Seats | Slack / webhooks | Digest | AI budget / month |
|------|-----------|--------|-------|------------------|--------|-------------------|
| free | 0 | 1 | 1 | no | weekly | $1 |
| starter | 49 | 5 | 3 | no | daily | $9 |
| team | 149 | 25 | 10 | yes | daily | $29 |

Limits answer `402 plan_limit_reached` with `{limit, plan, max}`. Plan changes go through
`POST /api/v1/workspaces/{id}/plan` (operator key): this is where a payment provider's webhook plugs in.
The AI budget is kept below 20% of the price, as the plan requires.

## AI cost per workspace

Every LLM call made *for* a workspace (site onboarding, reply drafts) is recorded with its
`workspace_id`. `GET /api/v1/workspace/usage` shows the month so far against the plan budget, and an
exhausted budget answers `402 llm_budget_exceeded`. Set `LLM_INPUT_USD_PER_MTOK` and
`LLM_OUTPUT_USD_PER_MTOK`: without prices the spend is unknown and nothing is blocked.

Classification is shared infrastructure (one pass over the corpus serves every workspace). To know the
cost per active workspace, add its share: shared classification cost from `GET /api/v1/usage/llm`
divided by the number of active topics, times the workspace's topics.

## Triage and the feedback loop

Signals are `new` until someone marks them `relevant`, `not_relevant` or `replied` (single or bulk).
The decisions are stored per workspace and, at each ingestion run, the latest ones per topic are shown to
the model as examples (`example the team judged relevant / NOT relevant`), so matching improves with use.
They are also labelled data for the evaluation set.

## Reply assistant

`POST /api/v1/inbox/{id}/reply-draft` writes a short reply that helps first, mentions the product only if
it fits, **always discloses the affiliation** (added in code if the model forgets) and carries the
community's rules (Reddit self-promotion limits, Hacker News etiquette, Stack Exchange disclosure).
unMeet never posts: the person reviews, edits and posts it.

## Deliveries

Email digests (SMTP, `python -m scripts.send_digests` hourly), Slack incoming webhooks, the existing
per-topic webhooks, and CSV export. The sent watermark moves only after the destination accepted the
message; errors are kept on the channel; plan rules are re-applied at send time.

## Not built yet (needs your decision or an account)

- Stripe: Checkout, customer portal, webhook → `set_plan`, tax. Live mode needs your explicit go.
- HubSpot / Pipedrive push: needs OAuth apps and sandbox accounts to test against.
- Sign-in button for the chosen auth provider (backend verification is done).
- Per-workspace allocation of shared classification cost in a report.
