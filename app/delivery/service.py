"""Daily/weekly digests of a workspace's new signals, by email and Slack.

Each channel is sent when due. The "sent" watermark only moves after the destination accepted
the message, so a failed send is retried at the next run instead of being lost, and the error is
kept on the channel for the owner to see. Digests contain only signals still in the "new" state,
so what a person already triaged is not repeated.
"""

from __future__ import annotations

import html
import logging
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, Protocol

import requests

from app.billing.plans import plan_for
from app.delivery.repository import ChannelStore
from app.delivery.schemas import Channel, validate_target
from app.inbox.schemas import InboxItem
from app.net.safe_fetch import Resolver
from app.tenancy.store import TenancyStore

logger = logging.getLogger(__name__)

MAX_ITEMS = 20


class InboxReader(Protocol):
    def list_items(
        self,
        workspace_id: int,
        topic_id: int | None = None,
        state: str = "new",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[InboxItem, ...]: ...


class EmailSender(Protocol):
    def send(self, to: str, subject: str, text: str, html_body: str) -> None: ...


@dataclass(frozen=True)
class DigestResult:
    channel_id: int
    workspace_id: int
    kind: str
    sent_items: int
    status: str  # "sent" | "skipped" | "failed"
    detail: str | None = None


class SmtpEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        use_starttls: bool = True,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._sender = sender
        self._starttls = use_starttls
        self._timeout = timeout_seconds

    def send(self, to: str, subject: str, text: str, html_body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._sender, to, subject
        message.set_content(text)
        message.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password or "")
            smtp.send_message(message)


def render_text(workspace_name: str, items: tuple[InboxItem, ...]) -> str:
    lines = [f"{len(items)} new conversation(s) for {workspace_name}", ""]
    for item in items:
        lines.append(f"[{item.topic_name}] {item.title}")
        if item.pain_quote:
            lines.append(f'  "{item.pain_quote}"')
        lines.append(f"  Why it matches: {item.relevance_reason}")
        lines.append(f"  {item.url}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(workspace_name: str, items: tuple[InboxItem, ...]) -> str:
    rows = []
    for item in items:
        quote = (
            f"<blockquote>{html.escape(item.pain_quote)}</blockquote>" if item.pain_quote else ""
        )
        rows.append(
            f"<p><strong>[{html.escape(item.topic_name)}]</strong> "
            f'<a href="{html.escape(item.url, quote=True)}">{html.escape(item.title)}</a>'
            f"{quote}<em>Why it matches:</em> {html.escape(item.relevance_reason)}</p>"
        )
    return f"<h2>{len(items)} new conversation(s) for {html.escape(workspace_name)}</h2>" + "".join(
        rows
    )


def render_slack(workspace_name: str, items: tuple[InboxItem, ...]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{len(items)} new conversation(s)"[:150]},
        }
    ]
    for item in items:
        quote = f"\n>{item.pain_quote}" if item.pain_quote else ""
        text = (
            f"*[{_slack(item.topic_name)}]* <{item.url}|{_slack(item.title)}>{_slack(quote)}\n"
            f"_Why it matches:_ {_slack(item.relevance_reason)}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}})
    return {"text": f"{len(items)} new conversation(s) for {workspace_name}", "blocks": blocks[:50]}


def _slack(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class DigestService:
    def __init__(
        self,
        channels: ChannelStore,
        inbox: InboxReader,
        tenancy: TenancyStore,
        email_sender: EmailSender | None = None,
        session: Any | None = None,
        resolver: Resolver | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        timeout_seconds: float = 15.0,
    ) -> None:
        self._channels = channels
        self._inbox = inbox
        self._tenancy = tenancy
        self._email = email_sender
        self._session = session or requests.Session()
        self._resolver = resolver
        self._clock = clock
        self._timeout = timeout_seconds

    def send_due(self) -> tuple[DigestResult, ...]:
        now = self._clock()
        return tuple(
            self._send(channel, now) for channel in self._channels.list() if channel.is_due(now)
        )

    def _send(self, channel: Channel, now: datetime) -> DigestResult:
        workspace = self._tenancy.get_workspace(channel.workspace_id)
        if workspace is None:
            return DigestResult(
                channel.id, channel.workspace_id, channel.kind, 0, "skipped", "workspace gone"
            )
        plan = plan_for(workspace.plan)
        # Plan rules apply at send time too: a downgrade must stop paid channels.
        if channel.kind == "slack" and not plan.webhooks:
            return self._fail(channel, "Slack delivery is not included in the plan", "skipped")
        if channel.frequency == "daily" and not plan.daily_digest:
            return self._fail(channel, "daily digests are not included in the plan", "skipped")
        items = self._inbox.list_items(channel.workspace_id, state="new", limit=MAX_ITEMS)
        if not items:
            # Nothing new: still count as handled so the next check waits a full interval.
            self._channels.mark_sent(channel.id, now)
            return DigestResult(
                channel.id, channel.workspace_id, channel.kind, 0, "skipped", "nothing new"
            )
        try:
            if channel.kind == "email":
                self._send_email(channel, workspace.name, items)
            else:
                self._send_slack(channel, workspace.name, items)
        except Exception as error:
            logger.warning("digest to channel %d failed: %s", channel.id, error)
            return self._fail(channel, str(error) or error.__class__.__name__, "failed")
        self._channels.mark_sent(channel.id, now)
        return DigestResult(channel.id, channel.workspace_id, channel.kind, len(items), "sent")

    def _fail(self, channel: Channel, error: str, status: str) -> DigestResult:
        self._channels.mark_failed(channel.id, error)
        return DigestResult(channel.id, channel.workspace_id, channel.kind, 0, status, error)

    def _send_email(self, channel: Channel, name: str, items: tuple[InboxItem, ...]) -> None:
        if self._email is None:
            raise RuntimeError("email is not configured (set SMTP_HOST and SMTP_FROM)")
        self._email.send(
            channel.target,
            f"{len(items)} new conversation(s) for {name}",
            render_text(name, items),
            render_html(name, items),
        )

    def _send_slack(self, channel: Channel, name: str, items: tuple[InboxItem, ...]) -> None:
        # Re-validate at send time: the stored URL's DNS may have changed since it was saved.
        url = validate_target("slack", channel.target, self._resolver)
        response = self._session.post(
            url, json=render_slack(name, items), timeout=self._timeout, allow_redirects=False
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Slack answered HTTP {response.status_code}")
