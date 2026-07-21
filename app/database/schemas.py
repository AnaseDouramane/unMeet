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
    is_problem: bool | None
    problem_confidence: float | None
    problem_reason: str | None
    problem_classifier: str | None
    classified_at: datetime | None
    embedding: tuple[float, ...] | None
    embedding_model: str | None
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
class PersistedClusterDetails:
    id: int
    run_id: int
    local_cluster_id: int
    label: str
    keywords: tuple[str, ...]
    centroid: tuple[float, ...]
    document_count: int


@dataclass(frozen=True)
class ClusterOpportunityStatistics:
    cluster_id: int
    source_count: int
    average_problem_confidence: float


@dataclass(frozen=True)
class ClusterRunMetadata:
    embedding_model: str
    min_cluster_size: int
    min_samples: int | None
    metric: str


@dataclass(frozen=True)
class PersistedClusterRun:
    id: int
    metadata: ClusterRunMetadata
    clusters: tuple[PersistedCluster, ...]
    created_at: datetime | None = None


@dataclass(frozen=True)
class PersistedClusterRunDetails:
    id: int
    created_at: datetime
    metadata: ClusterRunMetadata
