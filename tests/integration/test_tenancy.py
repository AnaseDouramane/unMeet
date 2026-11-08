"""The same behaviour is required from the in-memory store and the PostgreSQL repository."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.tenancy.repository import TenancyRepository
from app.tenancy.schemas import ConflictError, NotFoundError, Role
from app.tenancy.store import InMemoryTenancyStore
from tests.integration.conftest import TEST_DATABASE_URL


@pytest.fixture(params=["memory", "sql"])
def store(request):
    if request.param == "memory":
        return InMemoryTenancyStore()
    return TenancyRepository(request.getfixturevalue("session_factory"))


def test_creating_a_workspace_makes_the_creator_its_owner(store) -> None:
    workspace = store.create_workspace(" Acme Labs ", "Dana@Acme.test", "auth|1")

    assert (workspace.name, workspace.slug, workspace.plan) == ("Acme Labs", "acme-labs", "free")
    (member,) = store.list_members(workspace.id)
    assert (member.email, member.role) == ("dana@acme.test", Role.OWNER)
    assert store.role_of(workspace.id, member.user_id) is Role.OWNER
    assert [(w.id, r) for w, r in store.workspaces_for_user(member.user_id)] == [
        (workspace.id, Role.OWNER)
    ]


def test_slugs_stay_unique_and_names_are_validated(store) -> None:
    first = store.create_workspace("Acme", "a@acme.test")
    second = store.create_workspace("Acme", "b@acme.test")
    assert (first.slug, second.slug) == ("acme", "acme-2")
    with pytest.raises(ValueError):
        store.create_workspace("  ", "c@acme.test")
    with pytest.raises(ValueError):
        store.create_workspace("Ok", "not-an-email")


def test_users_are_matched_by_email_or_external_id_and_linked_later(store) -> None:
    invited = store.add_member(
        store.create_workspace("W", "o@w.test").id, "Eve@W.test", Role.MEMBER
    )
    # The invited person later logs in through the auth provider with the same email.
    user = store.get_or_create_user("eve@w.test", "auth|eve")
    assert user.id == invited.user_id and user.external_id == "auth|eve"
    assert store.get_or_create_user("other-email@w.test", "auth|eve").id == user.id


def test_members_cannot_be_duplicated_and_the_last_owner_cannot_leave(store) -> None:
    workspace = store.create_workspace("W", "owner@w.test")
    owner = store.list_members(workspace.id)[0]
    member = store.add_member(workspace.id, "m@w.test", Role.MEMBER)

    with pytest.raises(ConflictError):
        store.add_member(workspace.id, "M@w.test", Role.ADMIN)
    with pytest.raises(ConflictError):
        store.remove_member(workspace.id, owner.user_id)
    store.remove_member(workspace.id, member.user_id)
    with pytest.raises(NotFoundError):
        store.remove_member(workspace.id, member.user_id)
    assert [m.email for m in store.list_members(workspace.id)] == ["owner@w.test"]


def test_a_second_owner_lets_the_first_leave(store) -> None:
    workspace = store.create_workspace("W", "one@w.test")
    first = store.list_members(workspace.id)[0]
    store.add_member(workspace.id, "two@w.test", Role.OWNER)
    store.remove_member(workspace.id, first.user_id)
    assert [m.email for m in store.list_members(workspace.id)] == ["two@w.test"]


def test_api_keys_are_shown_once_authenticate_and_can_be_revoked(store) -> None:
    workspace = store.create_workspace("W", "o@w.test")
    other = store.create_workspace("Other", "o@other.test")
    info, plaintext = store.create_api_key(workspace.id, "ci")

    assert plaintext.startswith(f"um_{info.prefix}_")
    assert plaintext not in repr(info)
    assert store.authenticate_api_key(plaintext).workspace_id == workspace.id
    assert store.list_api_keys(workspace.id)[0].last_used_at is not None
    assert store.authenticate_api_key(plaintext + "x") is None
    assert store.authenticate_api_key("um_deadbeef_whatever") is None
    assert store.authenticate_api_key("garbage") is None

    with pytest.raises(NotFoundError):  # a key of another workspace cannot be revoked
        store.revoke_api_key(other.id, info.id)
    store.revoke_api_key(workspace.id, info.id)
    store.revoke_api_key(workspace.id, info.id)  # idempotent
    assert store.authenticate_api_key(plaintext) is None
    assert store.list_api_keys(workspace.id)[0].revoked_at is not None
    assert store.list_api_keys(other.id) == ()


def test_plan_changes_are_validated(store) -> None:
    workspace = store.create_workspace("W", "o@w.test")
    assert store.set_plan(workspace.id, "team").plan == "team"
    assert store.get_workspace(workspace.id).plan == "team"
    with pytest.raises(ValueError):
        store.set_plan(workspace.id, "enterprise")
    with pytest.raises(NotFoundError):
        store.set_plan(999, "free")
    assert store.get_workspace(999) is None


def test_default_workspace_is_created_once(store) -> None:
    assert store.ensure_default_workspace().id == store.ensure_default_workspace().id
    assert store.ensure_default_workspace().slug == "default"


def test_unknown_workspace_errors(store) -> None:
    with pytest.raises(NotFoundError):
        store.list_members(999)
    with pytest.raises(NotFoundError):
        store.create_api_key(999, "k")
    with pytest.raises(NotFoundError):
        store.add_member(999, "a@b.test", Role.MEMBER)


def test_migration_moves_existing_topics_into_a_default_workspace() -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    engine = create_engine(TEST_DATABASE_URL, future=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    config = Config("alembic.ini")
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "e5a0c3d8f412")  # the revision before workspaces
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tracked_topics (name, intents, products, sources, max_distance) "
                "VALUES ('Legacy', '[]', '[\"HubSpot\"]', '[]', 0.6)"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT t.name, w.slug FROM tracked_topics t "
                "JOIN workspaces w ON w.id = t.workspace_id"
            )
        ).one()
    assert tuple(row) == ("Legacy", "default")
    engine.dispose()


def test_workspace_profile_is_saved_and_trimmed(store) -> None:
    workspace = store.create_workspace("W", "o@w.test")
    updated = store.set_profile(workspace.id, "https://acme.test", "  We sell CRM cleaning.  ")
    assert (updated.website_url, updated.product_summary) == ("https://acme.test", "We sell CRM cleaning.")
    assert store.get_workspace(workspace.id).product_summary == "We sell CRM cleaning."
    assert store.set_profile(workspace.id, None, "  ").product_summary is None
    with pytest.raises(NotFoundError):
        store.set_profile(999, None, None)
