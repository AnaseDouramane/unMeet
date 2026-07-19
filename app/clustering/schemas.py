from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ClusterableDocument:
    id: int
    source: str
    external_id: str
    document_text: str
    embedding: tuple[float, ...]
    embedding_model: str


@dataclass(frozen=True)
class ClusterCentroid:
    cluster_id: int
    centroid: tuple[float, ...]


@dataclass(frozen=True)
class ClusterMatch:
    current_cluster_id: int
    previous_cluster_id: int | None
    similarity: float
    status: Literal["matched", "new"]


@dataclass(frozen=True)
class TrendCluster:
    id: int
    label: str
    document_count: int


@dataclass(frozen=True)
class ClusterTrend:
    current_cluster_id: int
    previous_cluster_id: int | None
    label: str
    current_count: int
    previous_count: int
    absolute_change: int
    growth_rate: float | None
    status: Literal["new", "rising", "stable", "falling"]
    similarity: float | None
