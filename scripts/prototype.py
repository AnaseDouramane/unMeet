"""Set up and fill a local prototype in one command, so you can try the product by hand.

  python -m scripts.prototype --owner you@company.com [--site https://yourproduct.com]

It (1) migrates the database, (2) creates a workspace with an API key (shown once),
(3) creates topics, from your website with the LLM when --site is given, otherwise a small example
set, (4) searches Hacker News for the topics' phrases and matches what it finds, and
(5) prints where to look. Needs DATABASE_URL, LLM_MODEL and LLM_API_KEY (a free Groq key works).
Safe to run again: topics and the workspace are reused, posts already seen are skipped.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from alembic import command

from app.config import Settings
from app.dogfood import DOGFOOD_TOPICS
from app.inbox.repository import InboxRepository
from app.tenancy.repository import TenancyRepository
from app.topics.repository import DuplicateTopicError, TopicRepository
from app.topics.schemas import TopicDefinition

WORKSPACE_NAME = "Prototype"


def _migrate() -> None:
    from scripts.init_db import alembic_config

    command.upgrade(alembic_config(), "head")


def _topics_from_site(
    settings: Settings, url: str, workspace_id: int
) -> tuple[str, list[TopicDefinition]]:
    from app.llm.client import ChatCompletionsClient
    from app.net.safe_fetch import SafeFetcher
    from app.onboarding.service import OnboardingService

    client = ChatCompletionsClient(
        settings.llm_model or "", settings.llm_base_url, settings.llm_api_key, purpose="onboarding"
    )
    proposal = OnboardingService(client, SafeFetcher()).analyze(url, workspace_id)
    print(f"What we understood: {proposal.product_summary}")
    if proposal.competitors:
        print(f"Competitors: {', '.join(proposal.competitors)}")
    definitions = [
        TopicDefinition(
            name=t.name,
            description=t.description,
            intents=t.intents,
            products=t.products,
            keywords=t.keywords,
        )
        for t in proposal.topics
    ]
    return proposal.product_summary, definitions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--owner", required=True, help="email of the workspace owner")
    parser.add_argument("--site", help="your website: topics are proposed from it")
    parser.add_argument("--days", type=int, default=90, help="how far back the first search looks")
    parser.add_argument("--limit", type=int, default=120, help="posts to fetch at most")
    parser.add_argument("--no-ingest", action="store_true", help="only set up, do not fetch")
    args = parser.parse_args(argv)

    settings = Settings()
    if not args.no_ingest and not (settings.llm_model and settings.llm_api_key):
        print(
            "Set LLM_MODEL and LLM_API_KEY in .env first (a free Groq key works).", file=sys.stderr
        )
        return 1

    _migrate()
    tenancy, topics = TenancyRepository(), TopicRepository()
    owner = tenancy.get_or_create_user(args.owner)
    workspace = next(
        (w for w, _ in tenancy.workspaces_for_user(owner.id) if w.name == WORKSPACE_NAME), None
    ) or tenancy.create_workspace(WORKSPACE_NAME, args.owner)
    if workspace.plan != "team":
        workspace = tenancy.set_plan(workspace.id, "team")

    summary = None
    if args.site:
        try:
            summary, definitions = _topics_from_site(settings, args.site, workspace.id)
        except Exception as error:  # fetch, safety check or model problems: say why and stop
            print(f"Could not read {args.site}: {error}", file=sys.stderr)
            return 1
    else:
        definitions = list(DOGFOOD_TOPICS)
        print(
            "No --site given: using the example topics (people looking for lead monitoring tools)."
        )
    if summary:
        tenancy.set_profile(workspace.id, args.site, summary)
    created = []
    for definition in definitions:
        try:
            topics.create(definition, workspace.id)
            created.append(definition.name)
        except DuplicateTopicError:
            pass
    print(f"Topics: {len(created)} new, {len(definitions) - len(created)} already there.")
    for topic in topics.list(workspace.id):
        print(f"  - {topic.name}: searches {list(topic.keywords) or '[none]'}")

    _, key = tenancy.create_api_key(workspace.id, "prototype")

    if not args.no_ingest:
        from scripts.run_unmeet import build_ingestion

        run_settings = replace(
            settings,
            enabled_sources=("hackernews_topics",),
            hackernews_search_lookback_seconds=args.days * 86400,
            hackernews_search_limit=args.limit,
            topic_gate_enabled=True,
        )
        ingestion = build_ingestion(run_settings)
        print(f"Searching Hacker News (last {args.days} days, up to {args.limit} posts)…")
        ingestion.pipeline.run(connector=ingestion.connectors[0])
        stats = ingestion.pipeline.last_run_stats
        if stats is not None:
            print(
                f"Fetched {stats.acquired_count}, dropped before the AI {stats.gated_out_count}, "
                f"AI requests {stats.llm_call_count}, errors {stats.classification_error_count}."
            )

    counts = InboxRepository().counts(workspace.id)
    print(f"\nInbox: {counts['new']} new conversation(s).")
    print(f"Workspace id: {workspace.id}")
    print(f"API key (shown once, paste it in the app): {key}")
    print("\nNext:")
    print("  API:      uvicorn app.api.app:create_app --factory --reload")
    print("  App:      cd frontend && npm install && npm run dev  ->  http://localhost:3000/inbox")
    print(f"  Digest:   python -m scripts.concierge digest --workspace {workspace.id} --drafts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
