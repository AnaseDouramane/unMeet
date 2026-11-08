"""Run the manual test by hand: produce a digest to email, then read the answers back.

  python -m scripts.concierge digest --workspace 1 --count 5 --out concierge
      writes digest-YYYY-MM-DD.md (paste into an email) and feedback-YYYY-MM-DD.csv
  python -m scripts.concierge results concierge/feedback-2026-11-09.csv --workspace 1
      reads the answers, updates the inbox states and prints the share of useful conversations
      with a 95% interval

Add --drafts to include an AI reply draft per conversation (uses the LLM, a few tokens each).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.concierge.service import (
    feedback_sheet,
    parse_feedback,
    render_digest,
    states_from_feedback,
    summarize,
)
from app.config import Settings
from app.inbox.repository import InboxRepository
from app.tenancy.repository import TenancyRepository


def _digest(args: argparse.Namespace) -> int:
    inbox, tenancy = InboxRepository(), TenancyRepository()
    workspace = tenancy.get_workspace(args.workspace)
    if workspace is None:
        print(f"Workspace {args.workspace} does not exist.", file=sys.stderr)
        return 1
    items = inbox.list_items(args.workspace, state="new", limit=args.count)
    if not items:
        print("The inbox has nothing new. Run scripts.prototype (or the worker) first.")
        return 0
    drafts: dict[int, str] = {}
    if args.drafts:
        from app.llm.client import ChatCompletionsClient
        from app.reply.service import ReplyAssistant, ReplyError

        settings = Settings()
        if not settings.llm_model:
            print("Set LLM_MODEL to write reply drafts.", file=sys.stderr)
            return 1
        assistant = ReplyAssistant(
            ChatCompletionsClient(
                settings.llm_model,
                settings.llm_base_url,
                settings.llm_api_key,
                purpose="reply_draft",
            )
        )
        for item in items:
            text = inbox.signal_text(args.workspace, item.signal_id) or item.title
            try:
                drafts[item.signal_id] = assistant.draft(
                    source=item.source,
                    post_text=text,
                    company=workspace.name,
                    product_summary=workspace.product_summary,
                    workspace_id=args.workspace,
                ).text
            except ReplyError as error:
                print(f"No draft for {item.signal_id}: {error}", file=sys.stderr)
    today = datetime.now(UTC)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    digest_path = out / f"digest-{today:%Y-%m-%d}.md"
    sheet_path = out / f"feedback-{today:%Y-%m-%d}.csv"
    digest_path.write_text(render_digest(items, workspace.name, today, drafts), encoding="utf-8")
    sheet_path.write_text(feedback_sheet(items), encoding="utf-8")
    print(f"Wrote {digest_path} and {sheet_path} ({len(items)} conversations).")
    print("Send the digest, then fill the 'useful' and 'would_reply' columns (yes/no).")
    return 0


def _results(args: argparse.Namespace) -> int:
    rows = parse_feedback(Path(args.sheet).read_text(encoding="utf-8"))
    summary = summarize(rows)
    if summary.answered == 0:
        print(f"No answers yet ({summary.unanswered} rows without a yes/no in 'useful').")
        return 0
    states = states_from_feedback(rows)
    inbox = InboxRepository()
    for state, ids in states.items():
        if ids:
            inbox.set_state(args.workspace, ids, state)
    assert summary.precision is not None and summary.low is not None and summary.high is not None
    print(f"Answered: {summary.answered} (unanswered: {summary.unanswered})")
    print(
        f"Useful: {summary.useful}/{summary.answered} = {summary.precision:.0%} "
        f"(95% interval {summary.low:.0%}-{summary.high:.0%})"
    )
    print(f"Would reply: {summary.would_reply}/{summary.answered}")
    print(f"Inbox updated: { {state: len(ids) for state, ids in states.items()} }")
    if summary.answered < 30:
        print("Small sample: the interval is wide. Collect more answers before deciding.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    digest = sub.add_parser("digest", help="write the digest and the feedback sheet")
    digest.add_argument("--workspace", type=int, required=True)
    digest.add_argument("--count", type=int, default=5)
    digest.add_argument("--out", default="concierge")
    digest.add_argument("--drafts", action="store_true")
    digest.set_defaults(handler=_digest)
    results = sub.add_parser("results", help="read the filled sheet back")
    results.add_argument("sheet")
    results.add_argument("--workspace", type=int, required=True)
    results.set_defaults(handler=_results)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
