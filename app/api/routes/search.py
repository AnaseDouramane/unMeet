from fastapi import APIRouter, Depends

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.routes.common import document_response
from app.api.schemas import SearchResponse


router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: str,
    limit: int = 10,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> SearchResponse:
    if not q.strip():
        raise ApiError(400, "invalid_query", "q must not be empty")
    if limit <= 0 or limit > 100:
        raise ApiError(400, "invalid_limit", "limit must be between 1 and 100")
    return SearchResponse(
        items=[document_response(item) for item in dependencies.semantic_search.search(q, limit)]
    )
