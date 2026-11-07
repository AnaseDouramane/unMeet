"""Send new signals for every tracked topic with a webhook. Schedule it after each run."""

from __future__ import annotations

import sys

from app.config import settings
from app.database.repository import SourceItemRepository
from app.embeddings.embedding_service import EmbeddingService
from app.signals.service import RepositorySignalReader
from app.topics.delivery import AlertDeliveryService
from app.topics.repository import TopicRepository


def main() -> int:
    service = AlertDeliveryService(
        TopicRepository(),
        RepositorySignalReader(EmbeddingService(settings.embedding_model), SourceItemRepository()),
    )
    results = service.deliver_all()
    for result in results:
        status = f"error: {result.error}" if result.error else f"{result.delivered_count} sent"
        print(f"[{result.topic_id}] {result.topic_name}: {status}")
    if not results:
        print("No topics with a webhook.")
    return 1 if any(result.error for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
