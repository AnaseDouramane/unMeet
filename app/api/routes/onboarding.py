from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.audit import record_audit
from app.api.budget import ensure_llm_budget
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.principal import require_manager
from app.api.routes.topics import _topic_response
from app.api.schemas import TopicResponse
from app.api.topic_service import ensure_topic_capacity
from app.llm.client import LLMRequestError
from app.net.safe_fetch import FetchError, UnsafeUrlError
from app.onboarding.service import OnboardingError
from app.tenancy.schemas import Principal
from app.topics.repository import DuplicateTopicError
from app.topics.schemas import TopicDefinition

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

ANALYSES_PER_HOUR = 10


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000, examples=["https://example.com"])


class TopicProposalModel(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    intents: list[str] = []
    products: list[str] = []


class ProposalResponse(BaseModel):
    source_url: str
    product_summary: str
    icp: str
    competitors: list[str]
    topics: list[TopicProposalModel]


class ConfirmRequest(BaseModel):
    website_url: str | None = Field(default=None, max_length=2000)
    product_summary: str | None = Field(default=None, max_length=1000)
    topics: list[TopicProposalModel] = Field(min_length=1, max_length=10)


class SkippedTopic(BaseModel):
    name: str
    reason: str


class ConfirmResponse(BaseModel):
    created: list[TopicResponse]
    skipped: list[SkippedTopic]


@router.post("/analyze", response_model=ProposalResponse)
def analyze(
    body: AnalyzeRequest,
    request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ProposalResponse:
    """Read the company's site and propose a summary, competitors and topics (nothing is saved)."""
    service = dependencies.onboarding
    if service is None:
        raise ApiError(503, "llm_not_configured", "set LLM_MODEL (and a key) to use onboarding")
    decision = request.app.state.onboarding_limiter.check(
        f"ws:{principal.workspace_id}", ANALYSES_PER_HOUR
    )
    if not decision.allowed:
        raise ApiError(
            429,
            "rate_limited",
            "too many site analyses this hour",
            {"retry_after_seconds": decision.retry_after_seconds},
        )
    ensure_llm_budget(dependencies, principal.workspace_id)
    try:
        proposal = service.analyze(body.url, principal.workspace_id)
    except UnsafeUrlError as error:
        raise ApiError(400, "unsafe_url", str(error)) from error
    except FetchError as error:
        raise ApiError(422, "fetch_failed", str(error)) from error
    except OnboardingError as error:
        raise ApiError(422, "analysis_failed", str(error)) from error
    except LLMRequestError as error:
        raise ApiError(
            502, "llm_unavailable", "the AI provider is unavailable, try again"
        ) from error
    return ProposalResponse(
        source_url=proposal.source_url,
        product_summary=proposal.product_summary,
        icp=proposal.icp,
        competitors=list(proposal.competitors),
        topics=[
            TopicProposalModel(
                name=t.name,
                description=t.description,
                intents=list(t.intents),
                products=list(t.products),
            )
            for t in proposal.topics
        ],
    )


@router.post("/confirm", response_model=ConfirmResponse, status_code=201)
def confirm(
    body: ConfirmRequest,
    request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ConfirmResponse:
    """Create the topics the user kept (edited as they like) and remember the product profile.

    Topics that do not fit the plan or are invalid are skipped and reported, not fatal.
    """
    created: list[TopicResponse] = []
    skipped: list[SkippedTopic] = []
    for proposal in body.topics:
        try:
            ensure_topic_capacity(dependencies, principal.workspace_id)
            definition = TopicDefinition(
                name=proposal.name,
                description=proposal.description,
                intents=tuple(proposal.intents),
                products=tuple(p.strip() for p in proposal.products if p.strip()),
            )
            topic = dependencies.topic_store.create(definition, principal.workspace_id)
        except ApiError as error:
            skipped.append(SkippedTopic(name=proposal.name, reason=error.message))
            continue
        except DuplicateTopicError:
            skipped.append(SkippedTopic(name=proposal.name, reason="a topic with this name exists"))
            continue
        except ValueError as error:
            skipped.append(SkippedTopic(name=proposal.name, reason=str(error)))
            continue
        created.append(_topic_response(topic))
        record_audit(
            request,
            dependencies,
            "topic.create",
            "topic",
            topic.id,
            {"name": topic.name, "via": "onboarding"},
            workspace_id=principal.workspace_id,
        )
    if body.website_url or body.product_summary:
        dependencies.tenancy.set_profile(
            principal.workspace_id, body.website_url, body.product_summary
        )
    return ConfirmResponse(created=created, skipped=skipped)
