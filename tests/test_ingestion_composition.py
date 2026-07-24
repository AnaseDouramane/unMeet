from __future__ import annotations

import pytest

from app.ingestion import factory
from app.services.ingestion_only import IngestionOnlyStats
from scripts import run_ingestion_only, run_unmeet


class FakeConnector:
    def __init__(self, source: str) -> None:
        self.source = source


class FakeIngestionService:
    def __init__(self) -> None:
        self.sources: list[str] = []

    def run(self, connector: FakeConnector) -> IngestionOnlyStats:
        self.sources.append(connector.source)
        return IngestionOnlyStats(acquired_count=1, new_count=1)


def _settings(sources: tuple[str, ...]):
    return type(
        "Settings",
        (),
        {
            "enabled_sources": sources,
            "hackernews_feeds": ("topstories",),
            "hackernews_limit": 3,
            "ingestion_fail_fast": False,
        },
    )()


def test_factory_builds_hackernews_and_github_in_configured_order(monkeypatch) -> None:
    built: list[str] = []
    monkeypatch.setattr(
        factory,
        "HackerNewsConnector",
        lambda **kwargs: built.append("hackernews") or FakeConnector("hackernews"),
    )
    monkeypatch.setattr(
        factory.GitHubIssuesConnector,
        "from_settings",
        lambda settings: built.append("github") or FakeConnector("github"),
    )

    connectors = factory.build_configured_connectors(_settings(("hackernews", "github")))
    service = FakeIngestionService()
    result = run_ingestion_only.run_ingestion(service, connectors, fail_fast=False)

    assert built == ["hackernews", "github"]
    assert service.sources == ["hackernews", "github"]
    assert result.acquired_count == 2
    assert [item.source for item in result.source_stats] == ["hackernews", "github"]


def test_factory_with_only_github_never_constructs_hackernews(monkeypatch) -> None:
    monkeypatch.setattr(
        factory,
        "HackerNewsConnector",
        lambda **kwargs: pytest.fail("Hacker News must not be constructed"),
    )
    github = FakeConnector("github")
    monkeypatch.setattr(factory.GitHubIssuesConnector, "from_settings", lambda settings: github)

    assert factory.build_configured_connectors(_settings(("github",))) == (github,)


def test_factory_does_not_construct_disabled_github(monkeypatch) -> None:
    hackernews = FakeConnector("hackernews")
    monkeypatch.setattr(factory, "HackerNewsConnector", lambda **kwargs: hackernews)
    monkeypatch.setattr(
        factory.GitHubIssuesConnector,
        "from_settings",
        lambda settings: pytest.fail("GitHub must not be constructed"),
    )

    assert factory.build_configured_connectors(_settings(("hackernews",))) == (hackernews,)


def test_factory_rejects_unknown_sources() -> None:
    with pytest.raises(ValueError, match="Unsupported ingestion source: unknown"):
        factory.build_configured_connectors(_settings(("unknown",)))


def test_both_entry_points_use_the_shared_factory(monkeypatch) -> None:
    assert run_unmeet.build_configured_connectors is factory.build_configured_connectors
    assert run_ingestion_only.build_configured_connectors is factory.build_configured_connectors
    connectors = (FakeConnector("github"),)
    monkeypatch.setattr(run_unmeet, "build_configured_connectors", lambda settings: connectors)
    monkeypatch.setattr(
        run_ingestion_only, "build_configured_connectors", lambda settings: connectors
    )

    assert run_unmeet.build_configured_connectors(_settings(("github",))) is connectors
    service, only_connectors, fail_fast = run_ingestion_only.build_application(_settings(("github",)))
    assert service is not None
    assert only_connectors is connectors
    assert fail_fast is False
