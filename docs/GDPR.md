# GDPR: processing record and operating procedures

> Engineering documentation, **not legal advice**. Before charging customers, have a lawyer
> confirm the legal basis, the controller/processor roles and the contracts listed below.

## 1. Record of processing (art. 30, controller view)

| Item | Content |
|------|---------|
| Purpose | Help B2B teams find public conversations where people describe a problem or ask for a tool |
| Data subjects | Authors of public posts/comments on the configured sources |
| Personal data | Public username, public text, post URL, publication time; derived: intent, short quote, products mentioned, severity, topic-match reasons |
| Not collected | Private messages, emails, anything behind a login, data from sites whose terms forbid it |
| Source of data | Public APIs of Hacker News, Reddit (OAuth), GitHub, Stack Exchange |
| Legal basis | Legitimate interest (art. 6(1)(f)); balancing test and objection handling below |
| Recipients | Customers (public text, link, username of matched items), LLM provider (text sent for analysis), hosting and database providers (processors) |
| Transfers outside the EU | Depends on the chosen LLM and hosting providers; record the mechanism (SCCs / adequacy) when they are chosen |
| Retention | Non-signals `RETENTION_NON_SIGNAL_DAYS` (default 30), signals `RETENTION_SIGNAL_DAYS` (default 365); enforced by `python -m scripts.enforce_retention` |
| Security | API key on writes, per-client rate limiting, SSRF-safe webhooks, audit log of writes, secrets in the platform, no personal data in logs (clients appear as hashes) |

## 2. Rights

| Right | How it is served |
|-------|------------------|
| Erasure / objection | `POST /api/v1/privacy/erasure {source, author}` or `python -m scripts.erase_author <source> <username>`. Deletes every item of the author (clusters and topic matches cascade) and stores only a SHA-256 of the lowercased username, so the pipeline skips them from then on. The audit entry records the count, not the name. |
| Access / rectification | Answer from the database by `(source, author)`: `source_items` and `signal_topic_matches`. Rectification of public text is not applicable: the source is the authority. |
| Restriction | Same mechanism as erasure (suppress), unless the person asks to keep the data but stop using it: handle manually. |
| Information (art. 14) | `/privacy` page in the frontend. Configure `NEXT_PUBLIC_CONTROLLER_NAME` and `NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL`; the page shows a warning while they are empty. |

Respond to requests within one month. Keep a log of requests and outcomes (the audit trail covers erasures).

## 3. Legitimate-interest balancing (draft to review)

- Necessity: the product cannot work without reading the public text and its author handle.
- Expectations: posts are public and on forums where replies and monitoring by third parties are normal; unMeet never posts, messages or contacts anyone on its own.
- Safeguards: short retention, erasure on request with suppression, minimal fields, no sensitive-category targeting, quotes are verbatim and linked to the source.
- Risk: moderate. Re-evaluate before adding sources with sensitive content. A DPIA is recommended before large-scale use.

## 4. Before selling

- [ ] Fill in the controller identity and contact, publish `/privacy`.
- [ ] Data processing agreements with the LLM, hosting and database providers; record transfer mechanisms.
- [ ] Customer terms that make each customer a controller of its own outreach (and require compliance with the platforms' rules and the ePrivacy / anti-spam laws that apply to them).
- [ ] Verify the Reddit Data API terms for commercial use, and each other source's terms.
- [ ] Schedule `enforce_retention` daily.
- [ ] Decide who answers privacy requests and test the erasure flow on staging.
