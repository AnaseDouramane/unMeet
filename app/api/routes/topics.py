from fastapi import APIRouter, Depends, Query, Response

from app.api.auth import require_api_key
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.routes.signals import _signal_response
from app.api.schemas import (
    SignalListResponse,
    TopicCreateRequest,
    TopicListResponse,
    TopicResponse,
)
from app.signals.schemas import MAX_SIGNAL_LIMIT
from app.topics.matching import topic_signal_query
from app.topics.repository import DuplicateTopicError
from app.topics.schemas import Topic, TopicDefinition

router = APIRouter(prefix="/api/v1/topics", tags=["topics"])


def _topic_response(topic: Topic) -> TopicResponse:
    return TopicResponse(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        intents=list(topic.intents),
        products=list(topic.products),
        sources=list(topic.sources),
        min_severity=topic.min_severity,
        max_distance=topic.max_distance,
        has_webhook=topic.webhook_url is not None,
        created_at=topic.created_at,
        last_delivered_at=topic.last_delivered_at,
    )


def _get_topic(dependencies: ApiDependencies, topic_id: int) -> Topic:
    topic = dependencies.topic_store.get(topic_id)
    if topic is None:
        raise ApiError(404, "topic_not_found", f"topic {topic_id} does not exist")
    return topic


@router.get("", response_model=TopicListResponse)
def list_topics(dependencies: ApiDependencies = Depends(get_dependencies)) -> TopicListResponse:
    return TopicListResponse(items=[_topic_response(t) for t in dependencies.topic_store.list()])


@router.post(
    "",
    response_model=TopicResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_topic(
    request: TopicCreateRequest,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> TopicResponse:
    try:
        definition = TopicDefinition(
            name=request.name,
            description=request.description.strip() if request.description else None,
            intents=tuple(request.intents),
            products=tuple(p.strip() for p in request.products if p.strip()),
            sources=tuple(s.strip().lower() for s in request.sources if s.strip()),
            min_severity=request.min_severity,
            max_distance=request.max_distance,
            webhook_url=request.webhook_url,
        )
        return _topic_response(dependencies.topic_store.create(definition))
    except DuplicateTopicError as error:
        raise ApiError(409, "topic_exists", str(error)) from error
    except ValueError as error:
        raise ApiError(400, "invalid_topic", str(error)) from error


@router.delete("/{topic_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_topic(
    topic_id: int, dependencies: ApiDependencies = Depends(get_dependencies)
) -> Response:
    if not dependencies.topic_store.delete(topic_id):
        raise ApiError(404, "topic_not_found", f"topic {topic_id} does not exist")
    return Response(status_code=204)


@router.get("/{topic_id}/signals", response_model=SignalListResponse)
def topic_signals(
    topic_id: int,
    limit: int = Query(default=50, ge=1, le=MAX_SIGNAL_LIMIT),
    offset: int = Query(default=0, ge=0),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> SignalListResponse:
    topic = _get_topic(dependencies, topic_id)
    query, description = topic_signal_query(topic, limit=limit, offset=offset)
    signals = dependencies.signal_reader.find(query, description)
    return SignalListResponse(
        items=[_signal_response(signal) for signal in signals], limit=limit, offset=offset
    )
