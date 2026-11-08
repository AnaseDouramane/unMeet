"""Public "pain reports": one recurring problem, how it is trending and what people actually say.

Built from clusters. Everything shown is verbatim public text with a link to its source; author
names are never included. A cluster needs a minimum number of posts before it is published, so a
report is evidence of a pattern and not an anecdote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.analytics.schemas import ClusterRankingItem

MAX_QUOTES = 5
MAX_QUOTE_CHARS = 280


@dataclass(frozen=True)
class ReportQuote:
    source: str
    title: str
    url: str
    published_at: datetime
    text: str


@dataclass(frozen=True)
class Report:
    cluster_id: int
    title: str
    status: str
    growth_rate: float | None
    document_count: int
    source_count: int
    quotes: tuple[ReportQuote, ...]


@dataclass(frozen=True)
class ReportSummary:
    cluster_id: int
    title: str
    status: str
    growth_rate: float | None
    document_count: int
    source_count: int


def is_publishable(item: ClusterRankingItem, min_documents: int) -> bool:
    return item.document_count >= min_documents and bool(item.label.strip())


def summarize(item: ClusterRankingItem) -> ReportSummary:
    return ReportSummary(
        item.cluster_id,
        item.label.strip(),
        item.status,
        item.growth_rate,
        item.document_count,
        item.source_count,
    )


def _excerpt(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= MAX_QUOTE_CHARS:
        return cleaned
    return cleaned[: MAX_QUOTE_CHARS - 1].rstrip() + "…"


def build_report(item: ClusterRankingItem, documents: tuple) -> Report:
    """Pick up to five quotes, at most one per source URL, newest first."""
    quotes: list[ReportQuote] = []
    seen: set[str] = set()
    for document in documents:
        text = (getattr(document, "pain_quote", None) or document.title or "").strip()
        if not text or document.url in seen:
            continue
        seen.add(document.url)
        quotes.append(
            ReportQuote(
                source=document.source,
                title=document.title,
                url=document.url,
                published_at=document.published_at,
                text=_excerpt(text),
            )
        )
        if len(quotes) == MAX_QUOTES:
            break
    return Report(
        cluster_id=item.cluster_id,
        title=item.label.strip(),
        status=item.status,
        growth_rate=item.growth_rate,
        document_count=item.document_count,
        source_count=item.source_count,
        quotes=tuple(quotes),
    )


_TREND_WORDS = {
    "new": "new this period",
    "rising": "rising",
    "stable": "stable",
    "falling": "falling",
}


def render_markdown(report: Report, site_url: str | None = None) -> str:
    """A copy-ready version for newsletters, LinkedIn posts or a blog."""
    trend = _TREND_WORDS.get(report.status, report.status)
    growth = (
        f" ({report.growth_rate:+.0%} vs the previous period)"
        if report.growth_rate is not None
        else ""
    )
    lines = [
        f"# {report.title}",
        "",
        f"**{report.document_count} public posts** across **{report.source_count} "
        f"source{'s' if report.source_count != 1 else ''}** · trend: {trend}{growth}",
        "",
        "## What people are saying",
        "",
    ]
    for quote in report.quotes:
        lines.append(f"> {quote.text}")
        lines.append(f"> — [{quote.source}, {quote.published_at:%Y-%m-%d}]({quote.url})")
        lines.append("")
    footer = "Quotes are public posts, shown as written and linked to their source."
    if site_url:
        footer += f" Tracked with [unMeet]({site_url})."
    lines.append(f"*{footer}*")
    return "\n".join(lines) + "\n"
