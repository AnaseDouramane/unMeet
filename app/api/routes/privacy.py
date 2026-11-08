from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.audit import record_audit
from app.api.auth import require_api_key
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError

router = APIRouter(
    prefix="/api/v1/privacy", tags=["privacy"], dependencies=[Depends(require_api_key)]
)


class ErasureRequest(BaseModel):
    source: str = Field(min_length=1, max_length=50, examples=["reddit"])
    author: str = Field(min_length=1, max_length=255, examples=["some_username"])


class ErasureResponse(BaseModel):
    deleted_items: int


@router.post("/erasure", response_model=ErasureResponse)
def erase_author(
    body: ErasureRequest,
    http_request: Request,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ErasureResponse:
    """Delete everything stored about an author and stop ingesting their posts."""
    if not body.source.strip() or not body.author.strip():
        raise ApiError(400, "invalid_request", "source and author must not be blank")
    deleted = dependencies.privacy.erase_author(body.source, body.author)
    # The username itself is personal data: the audit trail records only the count.
    record_audit(
        http_request,
        dependencies,
        "privacy.erasure",
        "author",
        None,
        {"source": body.source.strip().lower(), "deleted_items": deleted},
    )
    return ErasureResponse(deleted_items=deleted)
