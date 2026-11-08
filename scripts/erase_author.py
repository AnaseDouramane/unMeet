"""Erase everything stored about an author: python -m scripts.erase_author reddit some_user"""

from __future__ import annotations

import sys

from app.privacy.service import PrivacyRepository


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m scripts.erase_author <source> <username>", file=sys.stderr)
        return 2
    deleted = PrivacyRepository().erase_author(argv[0], argv[1])
    print(f"Deleted {deleted} items; future posts by this author will be skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
