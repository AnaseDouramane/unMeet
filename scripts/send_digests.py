"""Send the daily/weekly digests that are due (run hourly).

Email needs SMTP_HOST and SMTP_FROM; Slack channels only need their webhook. A channel whose
send fails keeps its error and is retried at the next run.
"""

from __future__ import annotations

import logging
import sys

from app.config import Settings
from app.delivery.repository import ChannelRepository
from app.delivery.service import DigestService, SmtpEmailSender
from app.inbox.repository import InboxRepository
from app.tenancy.repository import TenancyRepository
from app.utils.logging import configure_logging


def main() -> int:
    configure_logging()
    settings = Settings()
    email = None
    if settings.smtp_host and settings.smtp_from:
        email = SmtpEmailSender(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from,
            settings.smtp_starttls,
        )
    else:
        logging.getLogger("unmeet.digest").warning(
            "SMTP is not configured: email digests will fail"
        )
    service = DigestService(ChannelRepository(), InboxRepository(), TenancyRepository(), email)
    results = service.send_due()
    for result in results:
        detail = f" ({result.detail})" if result.detail else ""
        print(
            f"channel {result.channel_id} [{result.kind}] ws {result.workspace_id}: {result.status}, {result.sent_items} items{detail}"
        )
    if not results:
        print("No digests due.")
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
