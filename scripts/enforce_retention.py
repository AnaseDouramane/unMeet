"""Delete items past their retention window (run daily).

Items that never became a signal are deleted after ``RETENTION_NON_SIGNAL_DAYS``; signals after
``RETENTION_SIGNAL_DAYS``. Age counts from when unMeet processed the item.
"""

from __future__ import annotations

import sys

from app.config import Settings
from app.privacy.service import PrivacyRepository


def main() -> int:
    settings = Settings()
    result = PrivacyRepository().enforce_retention(
        settings.retention_non_signal_days, settings.retention_signal_days
    )
    print(
        f"Retention: deleted {result.non_signals_deleted} non-signal items "
        f"(> {settings.retention_non_signal_days} days) and {result.signals_deleted} signals "
        f"(> {settings.retention_signal_days} days)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
