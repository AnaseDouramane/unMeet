from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.budget import ensure_llm_budget
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.principal import get_principal
from app.inbox.schemas import MAX_BULK, InboxItem
from app.llm.client import LLMRequestError
from app.reply.service import ReplyError
from app.tenancy.schemas import Principal

router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])

StateFilter = Literal["new", "relevant", "not_relevant", "replied", "all"]


class InboxItemResponse(BaseModel):
    signal_id: int
    source: str
    title: str
    url: str
    author: str | None
    published_at: datetime
    intent: str | None
    pain_quote: str | None
    products_mentioned: list[str]
    severity: int | None
    topic_id: int
    topic_name: str
    relevance_reason: str
    state: str
    note: str | None
    updated_at: datetime | None


class InboxListResponse(BaseModel):
    items: list[InboxItemResponse]
    limit: int
    offset: int


class InboxCountsResponse(BaseModel):
    new: int
    relevant: int
    not_relevant: int
    replied: int


class StateUpdateRequest(BaseModel):
    signal_ids: list[int] = Field(min_length=1, max_length=MAX_BULK)
    state: Literal["new", "relevant", "not_relevant", "replied"]
    note: str | None = Field(default=None, max_length=1000)
    topic_id: int | None = None


class StateUpdateResponse(BaseModel):
    updated: int


def _item_response(item: InboxItem) -> InboxItemResponse:
    return InboxItemResponse(
        signal_id=item.signal_id,
        source=item.source,
        title=item.title,
        url=item.url,
        author=item.author,
        published_at=item.published_at,
        intent=item.intent,
        pain_quote=item.pain_quote,
        products_mentioned=list(item.products_mentioned),
        severity=item.severity,
        topic_id=item.topic_id,
        topic_name=item.topic_name,
        relevance_reason=item.relevance_reason,
        state=item.state,
        note=item.note,
        updated_at=item.updated_at,
    )


@router.get("", response_model=InboxListResponse)
def list_inbox(
    topic_id: int | None = Query(default=None),
    state: StateFilter = Query(default="new"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> InboxListResponse:
    items = dependencies.inbox.list_items(principal.workspace_id, topic_id, state, limit, offset)
    return InboxListResponse(items=[_item_response(i) for i in items], limit=limit, offset=offset)


@router.get("/counts", response_model=InboxCountsResponse)
def inbox_counts(
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> InboxCountsResponse:
    return InboxCountsResponse(**dependencies.inbox.counts(principal.workspace_id))


@router.post("/state", response_model=StateUpdateResponse)
def update_state(
    body: StateUpdateRequest,
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> StateUpdateResponse:
    """Mark signals relevant / not relevant / replied (or back to new), one or many at once.

    Every role can triage. Ids that are not in the workspace's inbox are ignored, so the
    ``updated`` count tells the caller how many were really changed.
    """
    if (
        body.topic_id is not None
        and dependencies.topic_store.get(body.topic_id, principal.workspace_id) is None
    ):
        raise ApiError(404, "topic_not_found", f"topic {body.topic_id} does not exist")
    try:
        updated = dependencies.inbox.set_state(
            principal.workspace_id,
            body.signal_ids,
            body.state,
            body.note,
            body.topic_id,
            principal.user_id,
        )
    except ValueError as error:
        raise ApiError(400, "invalid_state", str(error)) from error
    return StateUpdateResponse(updated=updated)


class ReplyDraftResponse(BaseModel):
    draft: str
    mentions_product: bool
    disclosure_added: bool
    community_rules: str
    note: str = "Review and edit it, then post it yourself. unMeet never posts for you."


@router.post("/{signal_id}/reply-draft", response_model=ReplyDraftResponse)
def reply_draft(
    signal_id: int,
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ReplyDraftResponse:
    """A helpful, affiliation-disclosing draft reply to a signal in the caller's inbox."""
    assistant = dependencies.reply_assistant
    if assistant is None:
        raise ApiError(503, "llm_not_configured", "set LLM_MODEL (and a key) to draft replies")
    item = dependencies.inbox.get_item(principal.workspace_id, signal_id)
    text = dependencies.inbox.signal_text(principal.workspace_id, signal_id)
    if item is None or not text:
        raise ApiError(404, "signal_not_found", f"signal {signal_id} is not in your inbox")
    workspace = dependencies.tenancy.get_workspace(principal.workspace_id)
    ensure_llm_budget(dependencies, principal.workspace_id)
    try:
        draft = assistant.draft(
            source=item.source,
            post_text=text,
            company=workspace.name if workspace else "our company",
            product_summary=workspace.product_summary if workspace else None,
            workspace_id=principal.workspace_id,
        )
    except ReplyError as error:
        raise ApiError(422, "draft_failed", str(error)) from error
    except LLMRequestError as error:
        raise ApiError(
            502, "llm_unavailable", "the AI provider is unavailable, try again"
        ) from error
    return ReplyDraftResponse(
        draft=draft.text,
        mentions_product=draft.mentions_product,
        disclosure_added=draft.disclosure_added,
        community_rules=draft.community_rules,
    )
