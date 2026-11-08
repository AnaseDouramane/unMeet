from __future__ import annotations

from collections.abc import Sequence

from app.config import Settings
from app.ingestion.base import SourceConnector
from app.ingestion.github import GitHubIssuesConnector
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.hackernews_search import HackerNewsSearchConnector, SearchSpec
from app.ingestion.reddit import RedditConnector
from app.ingestion.stackexchange import StackExchangeConnector


def build_configured_connectors(settings: Settings) -> tuple[SourceConnector, ...]:
    """Build configured ingestion connectors in declared source order."""
    connectors: list[SourceConnector] = []
    for source in normalize_enabled_sources(settings.enabled_sources):
        if source == "hackernews":
            connectors.append(
                HackerNewsConnector(
                    feeds=settings.hackernews_feeds,
                    limit=settings.hackernews_limit,
                    max_workers=getattr(settings, "hackernews_max_workers", 1),
                    include_comments=getattr(settings, "hackernews_include_comments", False),
                    max_comments_per_story=getattr(
                        settings, "hackernews_max_comments_per_story", 20
                    ),
                )
            )
        elif source == "hackernews_search":
            connectors.append(
                HackerNewsSearchConnector(
                    searches=parse_search_specs(settings.hackernews_searches),
                    limit=settings.hackernews_search_limit,
                    lookback_seconds=settings.hackernews_search_lookback_seconds,
                )
            )
        elif source == "stackexchange":
            connectors.append(
                StackExchangeConnector(
                    site=settings.stackexchange_site,
                    queries=settings.stackexchange_queries or (None,),
                    limit=settings.stackexchange_limit,
                    key=settings.stackexchange_key,
                )
            )
        elif source == "reddit":
            connectors.append(RedditConnector.from_settings(settings))
        elif source == "github":
            connectors.append(GitHubIssuesConnector.from_settings(settings))
        else:
            raise ValueError(f"Unsupported ingestion source: {source}")
    if not connectors:
        raise ValueError("At least one ingestion source must be enabled")
    return tuple(connectors)


def parse_search_specs(raw_specs: Sequence[str]) -> tuple[SearchSpec, ...]:
    """Turn ``tag`` or ``tag:query`` strings into searches."""
    specs: list[SearchSpec] = []
    for raw in raw_specs:
        tag, _, query = raw.partition(":")
        specs.append(SearchSpec(tag=tag.strip().lower(), query=query.strip() or None))
    return tuple(specs)


def normalize_enabled_sources(sources: Sequence[str]) -> tuple[str, ...]:
    if isinstance(sources, (str, bytes)):
        raise TypeError("enabled_sources must be a sequence of source names")
    normalized_sources: list[str] = []
    seen_sources: set[str] = set()
    for source in sources:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("enabled source names must be non-empty strings")
        normalized_source = source.strip().lower()
        if normalized_source in seen_sources:
            raise ValueError(f"Duplicate ingestion source: {normalized_source}")
        seen_sources.add(normalized_source)
        normalized_sources.append(normalized_source)
    return tuple(normalized_sources)
