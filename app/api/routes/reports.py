from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.reports.service import Report, build_report, is_publishable, render_markdown, summarize

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

CACHE = {"Cache-Control": "public, max-age=300"}


class ReportSummaryResponse(BaseModel):
    cluster_id: int
    title: str
    status: str
    growth_rate: float | None
    document_count: int
    source_count: int


class ReportListResponse(BaseModel):
    items: list[ReportSummaryResponse]


class QuoteResponse(BaseModel):
    source: str
    title: str
    url: str
    published_at: datetime
    text: str


class ReportResponse(ReportSummaryResponse):
    quotes: list[QuoteResponse]


def _minimum(request: Request) -> int:
    return int(request.app.state.settings.report_min_documents)


def _report(request: Request, dependencies: ApiDependencies, cluster_id: int) -> Report:
    item = next(
        (c for c in dependencies.analytics_reader.get_clusters() if c.cluster_id == cluster_id),
        None,
    )
    if item is None or not is_publishable(item, _minimum(request)):
        raise ApiError(404, "report_not_found", f"report {cluster_id} does not exist")
    detail = dependencies.analytics_reader.get_cluster(cluster_id, document_limit=30)
    return build_report(item, detail.documents if detail else ())


@router.get("", response_model=ReportListResponse)
def list_reports(
    request: Request,
    response: Response,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ReportListResponse:
    """Recurring problems with enough evidence to publish, best opportunities first."""
    response.headers.update(CACHE)
    minimum = _minimum(request)
    ranked = sorted(
        (c for c in dependencies.analytics_reader.get_clusters() if is_publishable(c, minimum)),
        key=lambda c: (-c.opportunity_score, c.cluster_id),
    )
    return ReportListResponse(items=[ReportSummaryResponse(**vars(summarize(c))) for c in ranked])


@router.get("/{cluster_id}.md", response_class=PlainTextResponse)
def report_markdown(
    cluster_id: int,
    request: Request,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> PlainTextResponse:
    report = _report(request, dependencies, cluster_id)
    site = request.app.state.settings.public_site_url
    return PlainTextResponse(
        render_markdown(report, site),
        media_type="text/markdown; charset=utf-8",
        headers=CACHE,
    )


@router.get("/{cluster_id}", response_model=ReportResponse)
def get_report(
    cluster_id: int,
    request: Request,
    response: Response,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ReportResponse:
    response.headers.update(CACHE)
    report = _report(request, dependencies, cluster_id)
    return ReportResponse(
        cluster_id=report.cluster_id,
        title=report.title,
        status=report.status,
        growth_rate=report.growth_rate,
        document_count=report.document_count,
        source_count=report.source_count,
        quotes=[QuoteResponse(**vars(q)) for q in report.quotes],
    )
