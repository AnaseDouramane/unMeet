"""Serve the API with the configured logging: python -m scripts.run_api"""

from __future__ import annotations

import uvicorn

from app.config import Settings
from app.utils.logging import configure_logging


def main() -> int:
    settings = Settings()
    configure_logging()
    uvicorn.run(
        "app.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # keep our logging configuration (JSON when LOG_FORMAT=json)
        proxy_headers=settings.trust_proxy_headers,
        forwarded_allow_ips="*" if settings.trust_proxy_headers else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
