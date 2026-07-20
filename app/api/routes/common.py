from app.analytics.schemas import ClusterRankingItem
from app.api.dependencies import PublicDocument
from app.api.schemas import OpportunityResponse, PublicDocumentResponse, TrendDistributionResponse


def opportunity_response(item: ClusterRankingItem) -> OpportunityResponse:
    return OpportunityResponse(
        cluster_id=item.cluster_id,
        label=item.label,
        rank=item.rank,
        opportunity_score=item.opportunity_score,
        document_count=item.document_count,
        growth_rate=item.growth_rate,
        status=item.status,
        source_count=item.source_count,
        average_problem_confidence=item.average_problem_confidence,
        keywords=list(item.keywords),
    )


def document_response(item: PublicDocument) -> PublicDocumentResponse:
    return PublicDocumentResponse(
        id=item.id,
        source=item.source,
        title=item.title,
        body=item.body,
        url=item.url,
        author=item.author,
        published_at=item.published_at,
        problem_confidence=item.problem_confidence,
    )


def trend_distribution_response(trends: object) -> TrendDistributionResponse:
    return TrendDistributionResponse(
        new_count=trends.new_count,
        rising_count=trends.rising_count,
        stable_count=trends.stable_count,
        falling_count=trends.falling_count,
    )
