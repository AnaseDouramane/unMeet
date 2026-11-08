import time
from dataclasses import replace

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.audit.log import InMemoryAuditLog
from app.auth.jwt import InvalidTokenError, JwtVerifier
from app.config import settings as base_settings
from app.tenancy.schemas import Role
from app.tenancy.store import InMemoryTenancyStore
from app.topics.store import InMemoryTopicStore

SECRET = "x" * 40
ISSUER = "https://auth.example.test"
AUDIENCE = "unmeet"
OPERATOR_KEY = "operator-key-123"


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


def token(email="dana@acme.test", sub="auth|dana", **overrides) -> str:
    claims = {
        "sub": sub,
        "email": email,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def bearer(value: str, workspace: int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {value}"}
    if workspace is not None:
        headers["X-Workspace-ID"] = str(workspace)
    return headers


@pytest.fixture
def env():
    tenancy, audit = InMemoryTenancyStore(), InMemoryAuditLog()
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            topic_store=InMemoryTopicStore(),
            tenancy=tenancy,
            audit_log=audit,
            token_verifier=JwtVerifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE),
        ),
        settings=replace(
            base_settings,
            api_key=OPERATOR_KEY,
            environment="production",
            rate_limit_read_per_minute=0,
            rate_limit_write_per_minute=0,
        ),
    )
    client = TestClient(app)
    client.tenancy, client.audit = tenancy, audit  # type: ignore[attr-defined]
    return client


def topic(name="CRM", **extra):
    return {"name": name, "description": "crm hygiene", **extra}


def make_workspace(env, email="dana@acme.test", name="Acme", sub="auth|dana") -> int:
    response = env.post(
        "/api/v1/workspaces", json={"name": name}, headers=bearer(token(email, sub))
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# -- JWT verification --------------------------------------------------------------------------


def verifier(**kwargs) -> JwtVerifier:
    return JwtVerifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE, **kwargs)


def test_valid_token_yields_subject_and_lowercased_email() -> None:
    claims = verifier().verify(token(email="Dana@Acme.Test"))
    assert (claims.subject, claims.email) == ("auth|dana", "dana@acme.test")


@pytest.mark.parametrize(
    "bad",
    [
        token(exp=int(time.time()) - 3600),
        token(iss="https://evil.test"),
        token(aud="someone-else"),
        token(email=None),
        token(sub=None),
        token(email_verified=False),
        jwt.encode(
            {
                "sub": "x",
                "email": "a@b.test",
                "iss": ISSUER,
                "aud": AUDIENCE,
                "exp": int(time.time()) + 60,
            },
            "wrong-secret-wrong-secret-wrong-secret",
            algorithm="HS256",
        ),
        "not-a-jwt",
    ],
)
def test_invalid_tokens_are_rejected(bad: str) -> None:
    with pytest.raises(InvalidTokenError):
        verifier().verify(bad)


def test_unsigned_tokens_are_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": "x",
            "email": "a@b.test",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 60,
        },
        None,
        algorithm="none",
    )
    with pytest.raises(InvalidTokenError):
        verifier().verify(forged)
    with pytest.raises(ValueError):
        JwtVerifier(secret=SECRET, algorithms=("none",))


def test_verifier_needs_exactly_one_key_source() -> None:
    with pytest.raises(ValueError):
        JwtVerifier()
    with pytest.raises(ValueError):
        JwtVerifier(secret=SECRET, jwks_url="https://x.test/jwks")


# -- login and workspaces ----------------------------------------------------------------------


def test_creating_a_workspace_makes_you_owner_and_it_is_found_without_a_header(env) -> None:
    workspace_id = make_workspace(env)
    headers = bearer(token())

    current = env.get("/api/v1/workspace", headers=headers).json()
    assert (current["id"], current["role"], current["plan"]["name"]) == (
        workspace_id,
        "owner",
        "free",
    )
    assert current["seats_used"] == 1 and current["topics_used"] == 0
    assert [w["id"] for w in env.get("/api/v1/workspaces", headers=headers).json()] == [
        workspace_id
    ]


def test_credentials_are_required_and_garbage_is_rejected(env) -> None:
    assert env.get("/api/v1/workspace").status_code == 401
    assert env.get("/api/v1/workspace", headers=bearer("garbage")).status_code == 401
    assert env.get("/api/v1/workspace", headers=bearer(token(exp=1))).status_code == 401
    assert env.get("/api/v1/workspaces").status_code == 401
    # Workspace API keys cannot be used where a logged-in person is needed.
    workspace = env.tenancy.ensure_default_workspace().id
    _, key = env.tenancy.create_api_key(workspace, "k")
    assert env.get("/api/v1/workspaces", headers={"X-API-Key": key}).status_code == 401


def test_a_user_without_a_workspace_or_with_several_must_choose(env) -> None:
    assert (
        env.get("/api/v1/workspace", headers=bearer(token())).json()["code"] == "workspace_required"
    )
    first, second = make_workspace(env, name="One"), make_workspace(env, name="Two")
    response = env.get("/api/v1/workspace", headers=bearer(token()))
    assert response.status_code == 400 and response.json()["code"] == "workspace_required"
    assert env.get("/api/v1/workspace", headers=bearer(token(), second)).json()["id"] == second
    assert first != second


def test_other_workspaces_look_like_they_do_not_exist(env) -> None:
    acme = make_workspace(env)
    outsider = bearer(token("eve@evil.test", "auth|eve"), acme)

    forbidden = env.get("/api/v1/topics", headers=outsider)
    missing = env.get("/api/v1/topics", headers=bearer(token("eve@evil.test", "auth|eve"), 999))
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json()["code"] == missing.json()["code"] == "workspace_not_found"
    assert (
        env.get("/api/v1/topics", headers={**bearer(token()), "X-Workspace-ID": "abc"}).status_code
        == 400
    )


# -- isolation ---------------------------------------------------------------------------------


def test_workspaces_cannot_see_or_touch_each_others_topics(env) -> None:
    acme = make_workspace(env)
    beta = make_workspace(env, "bob@beta.test", "Beta", "auth|bob")
    mine, theirs = bearer(token(), acme), bearer(token("bob@beta.test", "auth|bob"), beta)

    created = env.post("/api/v1/topics", json=topic(), headers=mine).json()

    assert env.get("/api/v1/topics", headers=theirs).json()["items"] == []
    assert env.get(f"/api/v1/topics/{created['id']}/signals", headers=theirs).status_code == 404
    assert env.delete(f"/api/v1/topics/{created['id']}", headers=theirs).status_code == 404
    assert len(env.get("/api/v1/topics", headers=mine).json()["items"]) == 1
    # The same topic name is fine in another workspace.
    assert env.post("/api/v1/topics", json=topic(), headers=theirs).status_code == 201


def test_api_keys_are_bound_to_their_workspace_and_revocation_works(env) -> None:
    acme = make_workspace(env)
    beta = make_workspace(env, "bob@beta.test", "Beta", "auth|bob")
    created = env.post(
        "/api/v1/workspace/api-keys", json={"name": "ci"}, headers=bearer(token(), acme)
    )
    key = created.json()["key"]
    env.post("/api/v1/topics", json=topic(), headers={"X-API-Key": key})

    assert [
        t["name"] for t in env.get("/api/v1/topics", headers={"X-API-Key": key}).json()["items"]
    ] == ["CRM"]
    # Choosing another workspace with a key is ignored: the key decides.
    other = {"X-API-Key": key, "X-Workspace-ID": str(beta)}
    assert [t["name"] for t in env.get("/api/v1/topics", headers=other).json()["items"]] == ["CRM"]

    listing = env.get("/api/v1/workspace/api-keys", headers=bearer(token(), acme)).json()
    assert key not in str(listing) and listing[0]["prefix"] == created.json()["prefix"]
    key_id = created.json()["id"]
    assert (
        env.delete(
            f"/api/v1/workspace/api-keys/{key_id}",
            headers=bearer(token("bob@beta.test", "auth|bob"), beta),
        ).status_code
        == 404
    )
    assert (
        env.delete(
            f"/api/v1/workspace/api-keys/{key_id}", headers=bearer(token(), acme)
        ).status_code
        == 204
    )
    assert env.get("/api/v1/topics", headers={"X-API-Key": key}).status_code == 401


def test_the_operator_key_can_act_in_any_workspace(env) -> None:
    acme = make_workspace(env)
    headers = {"X-API-Key": OPERATOR_KEY, "X-Workspace-ID": str(acme)}
    assert env.get("/api/v1/workspace", headers=headers).json()["id"] == acme
    assert (
        env.get("/api/v1/workspace", headers={**headers, "X-Workspace-ID": "999"}).status_code
        == 404
    )
    default = env.get("/api/v1/workspace", headers={"X-API-Key": OPERATOR_KEY}).json()
    assert default["name"] == "Default"


# -- roles, plans, members ---------------------------------------------------------------------


def add_member(env, workspace, email, role, owner=("dana@acme.test", "auth|dana")):
    return env.post(
        "/api/v1/workspace/members",
        json={"email": email, "role": role},
        headers=bearer(token(*owner), workspace),
    )


def test_plain_members_can_read_but_not_manage(env) -> None:
    acme = make_workspace(env)
    env.post(
        f"/api/v1/workspaces/{acme}/plan",
        json={"plan": "team"},
        headers={"X-API-Key": OPERATOR_KEY},
    )
    assert add_member(env, acme, "mia@acme.test", "member").status_code == 201
    member = bearer(token("mia@acme.test", "auth|mia"), acme)

    assert env.get("/api/v1/topics", headers=member).status_code == 200
    assert env.get("/api/v1/workspace/members", headers=member).status_code == 200
    for response in (
        env.post("/api/v1/topics", json=topic(), headers=member),
        env.post("/api/v1/workspace/api-keys", json={"name": "k"}, headers=member),
        env.get("/api/v1/workspace/api-keys", headers=member),
        env.post("/api/v1/workspace/members", json={"email": "x@acme.test"}, headers=member),
    ):
        assert response.status_code == 403 and response.json()["code"] == "forbidden"


def test_only_owners_add_owners_and_the_last_owner_cannot_leave(env) -> None:
    acme = make_workspace(env)
    env.post(
        f"/api/v1/workspaces/{acme}/plan",
        json={"plan": "team"},
        headers={"X-API-Key": OPERATOR_KEY},
    )
    assert add_member(env, acme, "ann@acme.test", "admin").status_code == 201
    admin = bearer(token("ann@acme.test", "auth|ann"), acme)

    promote = env.post(
        "/api/v1/workspace/members", json={"email": "z@acme.test", "role": "owner"}, headers=admin
    )
    assert promote.status_code == 403
    assert add_member(env, acme, "ann@acme.test", "member").status_code == 409  # duplicate

    owner_id = next(m.user_id for m in env.tenancy.list_members(acme) if m.role is Role.OWNER)
    last = env.delete(f"/api/v1/workspace/members/{owner_id}", headers=admin)
    assert last.status_code == 409 and last.json()["code"] == "last_owner"
    assert env.delete("/api/v1/workspace/members/999", headers=admin).status_code == 404


def test_free_plan_limits_topics_webhooks_and_seats_until_upgraded(env) -> None:
    acme = make_workspace(env)
    headers = bearer(token(), acme)

    assert env.post("/api/v1/topics", json=topic("One"), headers=headers).status_code == 201
    second = env.post("/api/v1/topics", json=topic("Two"), headers=headers)
    assert second.status_code == 402 and second.json()["code"] == "plan_limit_reached"
    assert second.json()["details"] == {"limit": "topics", "plan": "free", "max": 1}
    hook = env.post(
        "/api/v1/topics", json=topic("Hook", webhook_url="https://x.example/h"), headers=headers
    )
    assert hook.status_code == 402
    assert add_member(env, acme, "mia@acme.test", "member").json()["details"]["limit"] == "seats"

    # Plan changes are operator-only.
    assert (
        env.post(
            f"/api/v1/workspaces/{acme}/plan", json={"plan": "team"}, headers=headers
        ).status_code
        == 401
    )
    upgrade = env.post(
        f"/api/v1/workspaces/{acme}/plan",
        json={"plan": "team"},
        headers={"X-API-Key": OPERATOR_KEY},
    )
    assert upgrade.status_code == 200 and upgrade.json()["plan"]["name"] == "team"
    assert env.post("/api/v1/topics", json=topic("Two"), headers=headers).status_code == 201
    assert (
        env.post(
            "/api/v1/topics", json=topic("Hook", webhook_url="https://x.example/h"), headers=headers
        ).status_code
        == 201
    )
    assert add_member(env, acme, "mia@acme.test", "member").status_code == 201
    bad = env.post(
        f"/api/v1/workspaces/{acme}/plan",
        json={"plan": "gold"},
        headers={"X-API-Key": OPERATOR_KEY},
    )
    assert bad.status_code == 400
    assert (
        env.post(
            "/api/v1/workspaces/999/plan",
            json={"plan": "team"},
            headers={"X-API-Key": OPERATOR_KEY},
        ).status_code
        == 404
    )


def test_plans_are_public(env) -> None:
    plans = {p["name"]: p for p in env.get("/api/v1/plans").json()}
    assert plans["free"]["monthly_price_eur"] == 0 and plans["team"]["max_topics"] == 25


def test_workspace_writes_are_audited_with_their_workspace(env) -> None:
    acme = make_workspace(env)
    headers = bearer(token(), acme)
    env.post("/api/v1/workspace/api-keys", json={"name": "ci"}, headers=headers)
    env.post("/api/v1/topics", json=topic(), headers=headers)

    events = env.audit.list(workspace_id=acme)
    assert {e.action for e in events} >= {"workspace.create", "api_key.create", "topic.create"}
    assert all(e.workspace_id == acme for e in events)
    key_event = next(e for e in events if e.action == "api_key.create")
    assert set(key_event.details) == {"name", "prefix"}  # the key itself is never audited


def test_development_without_credentials_uses_the_default_workspace() -> None:
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            tenancy=InMemoryTenancyStore(),
        ),
        settings=replace(base_settings, api_key=None, environment="development"),
    )
    client = TestClient(app)
    assert client.get("/api/v1/workspace").json()["name"] == "Default"
    assert client.post("/api/v1/topics", json=topic()).status_code == 201
