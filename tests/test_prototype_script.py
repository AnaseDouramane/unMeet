from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.tenancy.store import InMemoryTenancyStore
from app.topics.store import InMemoryTopicStore
from scripts import prototype


@pytest.fixture
def world(monkeypatch):
    tenancy, topics = InMemoryTenancyStore(), InMemoryTopicStore()
    monkeypatch.setattr(prototype, "TenancyRepository", lambda: tenancy)
    monkeypatch.setattr(prototype, "TopicRepository", lambda: topics)
    monkeypatch.setattr(prototype, "_migrate", lambda: None)
    monkeypatch.setattr(
        prototype,
        "InboxRepository",
        lambda: SimpleNamespace(
            counts=lambda ws: {"new": 2, "relevant": 0, "not_relevant": 0, "replied": 0}
        ),
    )
    return tenancy, topics


def test_setup_only_creates_a_team_workspace_example_topics_and_one_key(
    world, monkeypatch, capsys
) -> None:
    tenancy, topics = world
    monkeypatch.setattr(
        prototype, "Settings", lambda: replace(Settings(), llm_model=None, llm_api_key=None)
    )

    assert prototype.main(["--owner", "Me@Acme.test", "--no-ingest"]) == 0

    out = capsys.readouterr().out
    ((workspace, _),) = tenancy.workspaces_for_user(tenancy.get_or_create_user("me@acme.test").id)
    assert workspace.name == "Prototype" and workspace.plan == "team"
    assert topics.count(workspace.id) == 4 and all(t.keywords for t in topics.list(workspace.id))
    assert "API key (shown once" in out and "um_" in out and "Inbox: 2 new" in out
    assert f"--workspace {workspace.id}" in out


def test_running_twice_reuses_the_workspace_and_topics(world, monkeypatch, capsys) -> None:
    tenancy, topics = world
    monkeypatch.setattr(
        prototype, "Settings", lambda: replace(Settings(), llm_model=None, llm_api_key=None)
    )
    prototype.main(["--owner", "me@acme.test", "--no-ingest"])
    prototype.main(["--owner", "me@acme.test", "--no-ingest"])

    user = tenancy.get_or_create_user("me@acme.test")
    assert len(tenancy.workspaces_for_user(user.id)) == 1
    assert topics.count(tenancy.workspaces_for_user(user.id)[0][0].id) == 4
    assert "0 new, 4 already there" in capsys.readouterr().out


def test_without_an_llm_configured_it_stops_before_doing_anything(
    world, monkeypatch, capsys
) -> None:
    tenancy, _ = world
    monkeypatch.setattr(
        prototype, "Settings", lambda: replace(Settings(), llm_model=None, llm_api_key=None)
    )
    assert prototype.main(["--owner", "me@acme.test"]) == 1
    assert "LLM_MODEL and LLM_API_KEY" in capsys.readouterr().err
    assert tenancy.get_or_create_user("me@acme.test").id  # nothing else was created for them


def test_topics_proposed_from_a_site_carry_keywords_and_the_profile_is_saved(
    world, monkeypatch, capsys
) -> None:
    from app.topics.schemas import TopicDefinition

    tenancy, topics = world
    monkeypatch.setattr(
        prototype, "Settings", lambda: replace(Settings(), llm_model="m", llm_api_key="k")
    )
    monkeypatch.setattr(
        prototype,
        "_topics_from_site",
        lambda settings, url, workspace_id: (
            "Acme cleans CRM data.",
            [
                TopicDefinition(
                    name="Dupes", description="d", keywords=("merge duplicate contacts",)
                )
            ],
        ),
    )
    assert (
        prototype.main(["--owner", "me@acme.test", "--site", "https://acme.test", "--no-ingest"])
        == 0
    )

    workspace = tenancy.workspaces_for_user(tenancy.get_or_create_user("me@acme.test").id)[0][0]
    assert tenancy.get_workspace(workspace.id).product_summary == "Acme cleans CRM data."
    assert topics.list(workspace.id)[0].keywords == ("merge duplicate contacts",)


def test_a_site_that_cannot_be_read_stops_with_the_reason(world, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        prototype, "Settings", lambda: replace(Settings(), llm_model="m", llm_api_key="k")
    )

    def boom(settings, url, workspace_id):
        raise RuntimeError("the host must be public")

    monkeypatch.setattr(prototype, "_topics_from_site", boom)
    assert (
        prototype.main(["--owner", "me@acme.test", "--site", "https://10.0.0.1", "--no-ingest"])
        == 1
    )
    assert "the host must be public" in capsys.readouterr().err


def test_migration_adopts_older_databases_through_init_db(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("scripts.init_db.main", lambda: calls.append("init_db"))
    prototype._migrate()
    assert calls == ["init_db"]


def test_a_database_that_cannot_be_adopted_stops_with_a_clear_way_out(monkeypatch) -> None:
    from sqlalchemy.exc import ProgrammingError

    class DuplicateTable(Exception):
        pass

    def broken() -> None:
        raise ProgrammingError("CREATE TABLE cluster_runs", {}, DuplicateTable("exists"))

    monkeypatch.setattr("scripts.init_db.main", broken)
    with pytest.raises(SystemExit) as stopped:
        prototype._migrate()
    assert "docker compose down -v" in str(stopped.value) and "DuplicateTable" in str(stopped.value)
