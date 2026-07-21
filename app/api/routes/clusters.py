from typing import Literal

from fastapi import APIRouter, Depends

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.routes.common import document_response, opportunity_response
from app.api.schemas import ClusterDetailResponse, ClusterListResponse, ClusterSortField, TrendStatus


router = APIRouter(prefix="/api/v1/clusters", tags=["clusters"])


def _validate_pagination(limit: int, offset: int = 0) -> None:
    if limit <= 0 or limit > 100:
        raise ApiError(400, "invalid_limit", "limit must be between 1 and 100")
    if offset < 0:
        raise ApiError(400, "invalid_offset", "offset must be non-negative")


@router.get("", response_model=ClusterListResponse)
def list_clusters(
    limit: int = 20,
    offset: int = 0,
    status: TrendStatus | None = None,
    sort_by: ClusterSortField = "document_count",
    order: Literal["asc", "desc"] = "desc",
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ClusterListResponse:
    _validate_pagination(limit, offset)
    clusters = dependencies.analytics_reader.get_clusters()
    if status is not None:
        clusters = [item for item in clusters if item.status == status]

    def sort_key(item):
        if sort_by == "growth_rate":
            return item.growth_rate if item.growth_rate is not None else float("-inf")
        return getattr(item, sort_by)

    clusters = sorted(clusters, key=lambda item: item.cluster_id)
    clusters = sorted(clusters, key=sort_key, reverse=order == "desc")
    page = clusters[offset : offset + limit]
    return ClusterListResponse(
        items=[opportunity_response(item) for item in page],
        limit=limit,
        offset=offset,
    )


@router.get("/{cluster_id}", response_model=ClusterDetailResponse)
def cluster_detail(
    cluster_id: int,
    document_limit: int = 20,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ClusterDetailResponse:
    _validate_pagination(document_limit)
    detail = dependencies.analytics_reader.get_cluster(cluster_id, document_limit=document_limit)
    if detail is None:
        raise ApiError(404, "cluster_not_found", "cluster was not found")
    return ClusterDetailResponse(
        cluster=opportunity_response(detail.cluster),
        documents=[document_response(item) for item in detail.documents],
    )
