"""Create the unMeet dogfood workspace and its topics: python -m scripts.seed_dogfood you@company.com

Safe to run again. Prints a workspace API key only when --new-key is given (shown once).
"""

from __future__ import annotations

import sys

from app.dogfood import seed_dogfood
from app.tenancy.repository import TenancyRepository
from app.topics.repository import TopicRepository


def main(argv: list[str]) -> int:
    emails = [a for a in argv if not a.startswith("--")]
    if len(emails) != 1:
        print("usage: python -m scripts.seed_dogfood <owner-email> [--new-key]", file=sys.stderr)
        return 2
    tenancy = TenancyRepository()
    result = seed_dogfood(tenancy, TopicRepository(), emails[0])
    print(
        f"Workspace {result.workspace.id} '{result.workspace.name}' ({result.workspace.plan} plan)"
    )
    print(f"Created topics: {', '.join(result.created_topics) or 'none'}")
    print(f"Already there: {', '.join(result.existing_topics) or 'none'}")
    if "--new-key" in argv:
        _, key = tenancy.create_api_key(result.workspace.id, "dogfood")
        print(f"API key (shown once): {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
