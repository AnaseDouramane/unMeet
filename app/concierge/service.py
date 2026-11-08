"""Manual-test tooling: a digest you send by hand and a feedback sheet that measures it.

The sales question is not "does the code work" but "do people find these conversations useful
and would they pay". The digest turns the inbox into an email you can send to a founder; the
sheet records, per conversation, whether it was useful and whether they would reply; reading
the sheet back updates the inbox states and reports the share of useful conversations with a
95% Wilson interval, so a handful of answers is not mistaken for a result.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime

from app.inbox.schemas import InboxItem

FEEDBACK_COLUMNS = (
    "signal_id",
    "topic",
    "source",
    "url",
    "quote",
    "why_it_matches",
    "useful",
    "would_reply",
    "notes",
)
_YES = {"y", "yes", "s", "si", "sì", "1", "true", "x"}
_NO = {"n", "no", "0", "false"}


@dataclass(frozen=True)
class FeedbackRow:
    signal_id: int
    useful: bool | None
    would_reply: bool | None
    notes: str


@dataclass(frozen=True)
class FeedbackSummary:
    answered: int
    useful: int
    would_reply: int
    precision: float | None
    low: float | None
    high: float | None
    unanswered: int


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a share; honest about small samples (10 answers are a wide band)."""
    if total <= 0:
        raise ValueError("total must be positive")
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def render_digest(
    items: tuple[InboxItem, ...],
    company: str,
    today: datetime,
    drafts: dict[int, str] | None = None,
) -> str:
    """Markdown you can paste into an email. Quotes are verbatim and linked to the source."""
    lines = [
        f"# {len(items)} conversation(s) for {company} — {today:%Y-%m-%d}",
        "",
        "People who, in public, describe a need that matches what you track. "
        "Tell me which ones are useful and which are noise: that is what improves the next list.",
        "",
    ]
    for number, item in enumerate(items, 1):
        lines.append(f"## {number}. {item.title}")
        lines.append(f"*{item.source}, {item.published_at:%Y-%m-%d}, topic: {item.topic_name}*")
        lines.append("")
        if item.pain_quote:
            lines.append(f"> {item.pain_quote}")
            lines.append("")
        lines.append(f"**Why it matches:** {item.relevance_reason}")
        lines.append("")
        lines.append(f"[Open the conversation]({item.url})")
        draft = (drafts or {}).get(item.signal_id)
        if draft:
            lines += ["", "**Reply draft** (edit it; it discloses who you are):", "", f"> {draft}"]
        lines.append("")
    lines.append("*Quotes are public posts, shown as written. Nothing was posted on your behalf.*")
    return "\n".join(lines) + "\n"


def feedback_sheet(items: tuple[InboxItem, ...]) -> str:
    """CSV with one row per conversation and empty answer columns to fill in."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(FEEDBACK_COLUMNS)
    for item in items:
        writer.writerow(
            (
                item.signal_id,
                item.topic_name,
                item.source,
                item.url,
                _cell(item.pain_quote or item.title),
                _cell(item.relevance_reason),
                "",
                "",
                "",
            )
        )
    return buffer.getvalue()


def _cell(value: str) -> str:
    """Neutralise spreadsheet formulas in text taken from public posts."""
    return "'" + value if value and value[0] in "=+-@\t\r" else value


def _answer(value: str) -> bool | None:
    cleaned = (value or "").strip().lower()
    if cleaned in _YES:
        return True
    if cleaned in _NO:
        return False
    return None


def parse_feedback(text: str) -> tuple[FeedbackRow, ...]:
    rows: list[FeedbackRow] = []
    for record in csv.DictReader(io.StringIO(text)):
        try:
            signal_id = int(record.get("signal_id", ""))
        except ValueError:
            continue
        rows.append(
            FeedbackRow(
                signal_id,
                _answer(record.get("useful", "")),
                _answer(record.get("would_reply", "")),
                (record.get("notes") or "").strip(),
            )
        )
    return tuple(rows)


def summarize(rows: tuple[FeedbackRow, ...]) -> FeedbackSummary:
    answered = [r for r in rows if r.useful is not None]
    useful = sum(1 for r in answered if r.useful)
    would_reply = sum(1 for r in answered if r.would_reply)
    if not answered:
        return FeedbackSummary(0, 0, 0, None, None, None, len(rows))
    low, high = wilson_interval(useful, len(answered))
    return FeedbackSummary(
        len(answered),
        useful,
        would_reply,
        useful / len(answered),
        low,
        high,
        len(rows) - len(answered),
    )


def states_from_feedback(rows: tuple[FeedbackRow, ...]) -> dict[str, list[int]]:
    """Inbox states implied by the answers: replied > relevant > not relevant."""
    states: dict[str, list[int]] = {"replied": [], "relevant": [], "not_relevant": []}
    for row in rows:
        if row.useful is None:
            continue
        if row.useful and row.would_reply:
            states["replied"].append(row.signal_id)
        elif row.useful:
            states["relevant"].append(row.signal_id)
        else:
            states["not_relevant"].append(row.signal_id)
    return states
