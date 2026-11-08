from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.principal import get_principal
from app.api.schemas import SignalIntentParam, SignalListResponse, SignalResponse
from app.signals.schemas import MAX_SIGNAL_LIMIT, Signal, SignalQuery
from app.signals.service import signals_to_csv

router = APIRouter(prefix="/api/v1", tags=["signals"])

_TOPIC_DESCRIPTION = (
    "Free-text description of the pain you care about (for example "
    "'duplicate contacts in HubSpot'); results are ranked by semantic similarity."
)


def _signal_query(
    intent: list[SignalIntentParam] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    product: list[str] | None = Query(default=None),
    min_severity: int | None = Query(default=None, ge=1, le=3),
    since: date | None = Query(default=None, description="Only signals published on or after"),
    max_distance: float = Query(default=0.6, gt=0, le=2),
    limit: int = Query(default=50, ge=1, le=MAX_SIGNAL_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> SignalQuery:
    try:
        return SignalQuery(
            intents=tuple(intent or ()),
            sources=tuple(value.strip().lower() for value in source or () if value.strip()),
            products=tuple(value.strip() for value in product or () if value.strip()),
            min_severity=min_severity,
            published_since=(
                None if since is None else datetime.combine(since, time.min, tzinfo=UTC)
            ),
            max_distance=max_distance,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise ApiError(400, "invalid_signal_query", str(error)) from error


def _signal_response(signal: Signal) -> SignalResponse:
    return SignalResponse(
        id=signal.id,
        source=signal.source,
        title=signal.title,
        url=signal.url,
        author=signal.author,
        published_at=signal.published_at,
        intent=signal.intent,
        pain_quote=signal.pain_quote,
        products_mentioned=list(signal.products_mentioned),
        severity=signal.severity,
        confidence=signal.confidence,
        similarity=signal.similarity,
        relevance_reason=signal.relevance_reason,
    )


@router.get("/signals", response_model=SignalListResponse, dependencies=[Depends(get_principal)])
def list_signals(
    query: SignalQuery = Depends(_signal_query),
    topic: str | None = Query(default=None, max_length=500, description=_TOPIC_DESCRIPTION),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> SignalListResponse:
    signals = dependencies.signal_reader.find(query, topic)
    return SignalListResponse(
        items=[_signal_response(signal) for signal in signals],
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/signals.csv", response_class=PlainTextResponse, dependencies=[Depends(get_principal)])
def export_signals(
    query: SignalQuery = Depends(_signal_query),
    topic: str | None = Query(default=None, max_length=500, description=_TOPIC_DESCRIPTION),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> PlainTextResponse:
    signals = dependencies.signal_reader.find(query, topic)
    return PlainTextResponse(
        signals_to_csv(signals),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="unmeet-signals.csv"'},
    )
