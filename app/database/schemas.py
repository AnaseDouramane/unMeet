from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class PersistedSourceItem:
    id: int
    external_id: str
    source: str
    raw_payload: Mapping[str, Any] | None
    title: str
    clean_title: str | None
    body: str
    clean_body: str | None
    url: str
    document_text: str | None
    embedding: tuple[float, ...] | None
    dedup_hash: str | None
    author: str | None
    published_at: datetime
    processed_at: datetime | None
    engagement_score: int | None


@dataclass(frozen=True)
class PersistedCluster:
    id: int
    run_id: int
    local_cluster_id: int


@dataclass(frozen=True)
class PersistedClusterRun:
    id: int
    clusters: tuple[PersistedCluster, ...]
