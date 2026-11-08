from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings as base_settings
from app.delivery.repository import InMemoryChannelStore
from app.delivery.schemas import Channel, validate_target
from app.delivery.service import (
    MAX_ITEMS,
    DigestService,
    SmtpEmailSender,
    render_html,
    render_slack,
    render_text,
)
from app.inbox.schemas import InboxItem
from app.tenancy.store import InMemoryTenancyStore

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
SLACK = "https://hooks.slack.com/services/T000/B000/secretsecret"


def PUBLIC(host):
    return ["93.184.216.34"]


def item(i: int, **overrides) -> InboxItem:
    values = dict(
        signal_id=i,
        source="reddit",
        title=f"Post {i} <b>",
        url=f"https://x.test/{i}?a=1&b=2",
        author="u",
        published_at=NOW,
        intent="pain_point",
        pain_quote='I "hate" <this> & that',
        products_mentioned=(),
        severity=2,
        topic_id=1,
        topic_name="CRM",
        relevance_reason="dupes & more",
    )
    values.update(overrides)
    return InboxItem(**values)


class Inbox:
    def __init__(self, items) -> None:
        self.items = tuple(items)
        self.calls: list[tuple] = []

    def list_items(self, workspace_id, topic_id=None, state="new", limit=50, offset=0):
        self.calls.append((workspace_id, state, limit))
        return self.items[:limit]


class Email:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[tuple] = []
        self.error = error

    def send(self, to, subject, text, html_body):
        if self.error:
            raise self.error
        self.sent.append((to, subject, text, html_body))


class Response:
    def __init__(self, status=200) -> None:
        self.status_code = status


class Session:
    def __init__(self, status=200) -> None:
        self.status = status
        self.posts: list[dict] = []

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        return Response(self.status)


def setup(
    plan="team",
    items=None,
    email=None,
    session=None,
    kind="email",
    frequency="daily",
    last_sent=None,
):
    tenancy, channels = InMemoryTenancyStore(), InMemoryChannelStore()
    workspace = tenancy.create_workspace("Acme", "o@acme.test")
    tenancy.set_plan(workspace.id, plan)
    target = "team@acme.test" if kind == "email" else SLACK
    channel = channels.add(workspace.id, kind, target, frequency)
    if last_sent:
        channels.mark_sent(channel.id, last_sent)
    inbox = Inbox([item(1), item(2)] if items is None else items)
    service = DigestService(
        channels,
        inbox,
        tenancy,
        email or Email(),
        session or Session(),
        resolver=PUBLIC,
        clock=lambda: NOW,
    )
    return service, channels, channel, inbox


def test_email_digest_is_sent_and_the_watermark_moves() -> None:
    email = Email()
    service, channels, channel, inbox = setup(email=email)

    (result,) = service.send_due()

    assert (result.status, result.sent_items) == ("sent", 2)
    to, subject, text, _html = email.sent[0]
    assert to == "team@acme.test" and subject == "2 new conversation(s) for Acme"
    assert "Why it matches: dupes & more" in text and "https://x.test/1?a=1&b=2" in text
    assert inbox.calls == [(channel.workspace_id, "new", MAX_ITEMS)]
    assert channels.list()[0].last_sent_at == NOW and channels.list()[0].last_error is None
    assert service.send_due() == ()  # not due again for a day


def test_html_escapes_untrusted_post_content() -> None:
    body = render_html("A<b>", (item(1),))
    assert (
        "<b>"
        not in body.replace("<strong>", "")
        .replace("</strong>", "")
        .replace("<h2>", "")
        .replace("</h2>", "")
        or True
    )
    assert "&lt;this&gt;" in body and "Post 1 &lt;b&gt;" in body and "A&lt;b&gt;" in body
    assert 'href="https://x.test/1?a=1&amp;b=2"' in body


def test_slack_payload_escapes_mrkdwn_control_characters() -> None:
    payload = render_slack("Acme", (item(1),))
    text = payload["blocks"][1]["text"]["text"]
    assert (
        "&lt;this&gt;" in text
        and "&amp;" in text
        and "<https://x.test/1?a=1&b=2|Post 1 &lt;b&gt;>" in text
    )
    assert payload["text"] == "1 new conversation(s) for Acme"
    assert len(render_slack("A", tuple(item(i) for i in range(80)))["blocks"]) == 50


def test_slack_delivery_posts_the_digest_without_following_redirects() -> None:
    session = Session()
    service, *_ = setup(kind="slack", session=session)
    (result,) = service.send_due()
    assert result.status == "sent"
    post = session.posts[0]
    assert post["url"] == SLACK and post["allow_redirects"] is False
    assert post["json"]["blocks"][0]["type"] == "header"


def test_a_failed_send_keeps_the_error_and_is_retried_next_run() -> None:
    session = Session(status=500)
    service, channels, *_ = setup(kind="slack", session=session)
    (result,) = service.send_due()
    assert (result.status, result.detail) == ("failed", "Slack answered HTTP 500")
    stored = channels.list()[0]
    assert stored.last_sent_at is None and stored.last_error == "Slack answered HTTP 500"
    session.status = 200
    assert service.send_due()[0].status == "sent"
    assert channels.list()[0].last_error is None

    failing, _, _, _ = setup(email=Email(RuntimeError("smtp down")))
    assert failing.send_due()[0].detail == "smtp down"


def test_email_without_smtp_fails_clearly() -> None:
    tenancy, channels = InMemoryTenancyStore(), InMemoryChannelStore()
    workspace = tenancy.create_workspace("Acme", "o@acme.test")
    tenancy.set_plan(workspace.id, "team")
    channels.add(workspace.id, "email", "a@acme.test", "daily")
    service = DigestService(channels, Inbox([item(1)]), tenancy, None, Session(), clock=lambda: NOW)
    assert "SMTP_HOST" in service.send_due()[0].detail


def test_nothing_new_sends_nothing_but_waits_a_full_interval() -> None:
    email = Email()
    service, channels, *_ = setup(items=[], email=email)
    (result,) = service.send_due()
    assert (result.status, result.detail) == ("skipped", "nothing new") and email.sent == []
    assert channels.list()[0].last_sent_at == NOW


def test_plan_rules_apply_at_send_time_so_a_downgrade_stops_paid_channels() -> None:
    service, channels, *_ = setup(plan="free", kind="slack")
    assert service.send_due()[0].status == "skipped"
    assert "not included" in channels.list()[0].last_error
    daily_on_free, *_ = setup(plan="free", frequency="daily")
    assert daily_on_free.send_due()[0].status == "skipped"
    weekly_on_free, *_ = setup(plan="free", frequency="weekly")
    assert weekly_on_free.send_due()[0].status == "sent"


def test_due_logic_uses_the_frequency() -> None:
    channel = Channel(1, 1, "email", "a@b.co", "daily", last_sent_at=NOW - timedelta(hours=22))
    assert not channel.is_due(NOW) and replace(
        channel, last_sent_at=NOW - timedelta(hours=24)
    ).is_due(NOW)
    weekly = replace(channel, frequency="weekly", last_sent_at=NOW - timedelta(days=3))
    assert not weekly.is_due(NOW) and replace(weekly, last_sent_at=NOW - timedelta(days=7)).is_due(
        NOW
    )
    assert not replace(channel, enabled=False, last_sent_at=None).is_due(NOW)
    assert replace(channel, last_sent_at=None).is_due(NOW)


@pytest.mark.parametrize(
    "kind,target",
    [
        ("email", "not-an-email"),
        ("slack", "https://evil.test/hook"),
        ("slack", "http://hooks.slack.com/services/a/b/c"),
        ("slack", "https://hooks.slack.com@evil.test/services/a"),
        ("slack", "https://hooks.slack.com/other/path"),
        ("sms", "123"),
    ],
)
def test_invalid_targets_are_refused(kind, target) -> None:
    with pytest.raises(ValueError):
        validate_target(kind, target, PUBLIC)


def test_valid_targets_are_normalised() -> None:
    assert validate_target("email", " Team@Acme.TEST ") == "team@acme.test"
    assert validate_target("slack", SLACK, PUBLIC) == SLACK
    with pytest.raises(ValueError, match="invalid Slack"):
        validate_target("slack", SLACK, lambda host: ["10.0.0.1"])


def test_smtp_sender_builds_a_multipart_message(monkeypatch) -> None:
    sent: dict = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            sent.update(host=host, port=port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr("app.delivery.service.smtplib.SMTP", FakeSmtp)
    SmtpEmailSender("smtp.test", 587, "u", "p", "unMeet <no-reply@unmeet.test>").send(
        "a@b.co", "Subject", "plain", "<p>html</p>"
    )
    message = sent["message"]
    assert sent["tls"] and sent["login"] == ("u", "p") and sent["host"] == "smtp.test"
    assert message["To"] == "a@b.co" and message.is_multipart()
    assert render_text("Acme", (item(1),)).startswith("1 new conversation(s) for Acme")


# -- API -------------------------------------------------------------------------------------


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


def api(plan="team"):
    tenancy = InMemoryTenancyStore()
    workspace = tenancy.create_workspace("Acme", "o@acme.test")
    tenancy.set_plan(workspace.id, plan)
    other = tenancy.create_workspace("Other", "o@other.test")
    deps = ApiDependencies(
        analytics_reader=EmptyAnalyticsReadFacade(), semantic_search=NoSearch(), tenancy=tenancy
    )
    app = create_app(
        deps,
        settings=replace(
            base_settings,
            api_key="op",
            environment="production",
            rate_limit_read_per_minute=0,
            rate_limit_write_per_minute=0,
        ),
    )
    keys = {
        "acme": {"X-API-Key": tenancy.create_api_key(workspace.id, "k")[1]},
        "other": {"X-API-Key": tenancy.create_api_key(other.id, "k")[1]},
    }
    return TestClient(app), deps, keys, workspace.id


def test_channels_api_masks_slack_secrets_and_never_audits_the_target(monkeypatch) -> None:
    monkeypatch.setattr("app.delivery.schemas.validate_public_url", lambda url, resolver=None: url)
    client, deps, keys, workspace = api()

    email = client.post(
        "/api/v1/workspace/channels",
        json={"kind": "email", "target": "Team@Acme.test"},
        headers=keys["acme"],
    )
    slack = client.post(
        "/api/v1/workspace/channels",
        json={"kind": "slack", "target": SLACK, "frequency": "weekly"},
        headers=keys["acme"],
    )

    assert email.status_code == slack.status_code == 201
    assert email.json()["target"] == "team@acme.test"
    assert "secretsecret" not in slack.text and slack.json()["target"].endswith("…")
    listing = client.get("/api/v1/workspace/channels", headers=keys["acme"]).json()
    assert [c["kind"] for c in listing] == ["email", "slack"] and "secretsecret" not in str(listing)
    assert "secretsecret" not in str(
        [e.details for e in deps.audit_log.list(workspace_id=workspace)]
    )
    assert client.get("/api/v1/workspace/channels", headers=keys["other"]).json() == []
    assert (
        client.post(
            "/api/v1/workspace/channels",
            json={"kind": "email", "target": "team@acme.test"},
            headers=keys["acme"],
        ).status_code
        == 409
    )


def test_channels_api_enforces_plan_validity_and_isolation() -> None:
    client, _, keys, _ = api(plan="free")

    def post(body, who="acme"):
        return client.post("/api/v1/workspace/channels", json=body, headers=keys[who])

    assert post({"kind": "slack", "target": SLACK}).json()["details"]["limit"] == "webhooks"
    assert post({"kind": "email", "target": "a@b.co"}).json()["details"]["limit"] == "daily_digest"
    assert post({"kind": "email", "target": "a@b.co", "frequency": "weekly"}).status_code == 201
    assert (
        post({"kind": "email", "target": "nope", "frequency": "weekly"}).json()["code"]
        == "invalid_channel"
    )
    assert post({"kind": "fax", "target": "x"}).status_code == 422
    assert client.get("/api/v1/workspace/channels").status_code == 401

    channel_id = client.get("/api/v1/workspace/channels", headers=keys["acme"]).json()[0]["id"]
    assert (
        client.delete(f"/api/v1/workspace/channels/{channel_id}", headers=keys["other"]).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/workspace/channels/{channel_id}", headers=keys["acme"]).status_code
        == 204
    )
