from __future__ import annotations

from collections.abc import Sequence

from app.config import Settings
from app.ingestion.base import SourceConnector
from app.ingestion.github import GitHubIssuesConnector
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.reddit import RedditConnector


def build_configured_connectors(settings: Settings) -> tuple[SourceConnector, ...]:
    """Build configured ingestion connectors in declared source order."""
    connectors: list[SourceConnector] = []
    for source in normalize_enabled_sources(settings.enabled_sources):
        if source == "hackernews":
            connectors.append(
                HackerNewsConnector(
                    feeds=settings.hackernews_feeds,
                    limit=settings.hackernews_limit,
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
