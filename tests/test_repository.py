from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm.exc import DetachedInstanceError

from app.clustering.schemas import ClusterableDocument
from app.clustering.service import DocumentCluster
from app.clustering.topic_labeling import TopicLabel
from app.database.models import ClusterModel, ClusterRunModel, SourceItemModel
from app.database.repository import ClusterRepository, SourceItemRepository
from app.database.schemas import PersistedCluster, PersistedClusterRun, PersistedSourceItem
from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeSession:
    def __init__(
        self,
        scalar_results: list[object | None] | None = None,
        scalars_results: list[list[object]] | None = None,
    ) -> None:
        self.scalar_results = scalar_results or []
        self.scalars_results = scalars_results or []
        self.scalars_statements = []
        self.added = []
        self.committed = 0
        self.rolled_back = 0
        self.refreshed = []
        self.closed = 0
        self.returned_models = []

    def get(self, model, primary_key):
        if not self.scalar_results:
            raise AssertionError(f"Unexpected get call: {model}, {primary_key}")
        result = self.scalar_results.pop(0)
        self.returned_models.append(result)
        return result

    def scalar(self, statement):
        if not self.scalar_results:
            raise AssertionError(f"Unexpected scalar call: {statement}")
        result = self.scalar_results.pop(0)
        self.returned_models.append(result)
        return result

    def scalars(self, statement):
        self.scalars_statements.append(statement)
        if not self.scalars_results:
            raise AssertionError(f"Unexpected scalars call: {statement}")
        rows = self.scalars_results.pop(0)
        self.returned_models.extend(rows)
        return FakeScalarResult(rows)

    def add(self, model):
        self.added.append(model)

    def flush(self):
        for model in self.added:
            if getattr(model, "id", None) is None:
                model.id = 101 if isinstance(model, ClusterModel) else 1

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def refresh(self, model):
        if getattr(model, "id", None) is None:
            model.id = 1
        self.refreshed.append(model)

    def close(self):
        self.closed += 1
        for model in self.returned_models:
            if hasattr(model, 'detach'):
                model.detach()


class FakeSessionFactory:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = sessions

    def __call__(self) -> FakeSession:
        if not self.sessions:
            raise AssertionError("Unexpected session request")
        return self.sessions.pop(0)


class FailingSessionFactory:
    def __call__(self):
        raise AssertionError("Session should not be opened for invalid input")


def _build_source_item(external_id: str = "123") -> SourceItem:
    return SourceItem(
        external_id=external_id,
        source="hackernews",
        title="Hello <b>HN</b>",
        body="<p>Body <i>content</i></p>",
        url="https://example.com/article",
        author="alice",
        published_at=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        engagement_score=42,
        raw_payload={"id": 123, "type": "story", "metadata": {"score": 42}},
    )


def _build_prepared_document(source_item: SourceItem, dedup_hash: str = "abc123") -> PreparedDocument:
    return PreparedDocument(
        source_item=source_item,
        title="Hello HN",
        body="Body content",
        document_text="Hello HN\n\nBody content",
        dedup_hash=dedup_hash,
    )


def _build_embedding(value: float = 0.1) -> list[float]:
    return [value] * 384


def _source_model(document_id: int = 1, value: float = 0.1) -> SourceItemModel:
    model = SourceItemModel()
    model.id = document_id
    model.source = "hackernews"
    model.external_id = str(document_id)
    model.raw_payload = {"metadata": {"score": 42}, "tags": ["cloud"]}
    model.title = "Cloud automation"
    model.clean_title = "Cloud automation"
    model.body = "Automate cloud operations"
    model.clean_body = "Automate cloud operations"
    model.url = "https://example.com/cloud"
    model.document_text = "cloud automation"
    model.embedding = _build_embedding(value)
    model.dedup_hash = f"hash-{document_id}"
    model.author = "alice"
    model.published_at = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
    model.processed_at = datetime.fromtimestamp(1_700_000_100, tz=timezone.utc)
    model.engagement_score = 42
    return model


class DetachableSourceItem:
    def __init__(self, model: SourceItemModel) -> None:
        self._detached = False
        for field in PersistedSourceItem.__dataclass_fields__:
            setattr(self, field, getattr(model, field))

    def detach(self) -> None:
        self._detached = True

    def __getattribute__(self, name: str):
        if name not in {"_detached", "detach", "__class__", "__dict__"}:
            if object.__getattribute__(self, "_detached"):
                raise DetachedInstanceError("source item is detached")
        return object.__getattribute__(self, name)


def _clusterable_document(document_id: int = 1, value: float = 0.1) -> ClusterableDocument:
    return ClusterableDocument(
        id=document_id,
        source="hackernews",
        external_id=str(document_id),
        document_text="cloud automation",
        embedding=tuple(_build_embedding(value)),
    )


def _assert_immutable_source_item(result: PersistedSourceItem) -> None:
    assert isinstance(result, PersistedSourceItem)
    assert not isinstance(result, SourceItemModel)
    assert result.embedding == tuple(_build_embedding())
    with pytest.raises(FrozenInstanceError):
        result.title = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.raw_payload["metadata"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        result.raw_payload["metadata"]["score"] = 0  # type: ignore[index]


def test_repository_persists_timezone_aware_timestamp_in_immutable_dto() -> None:
    session = FakeSession([None])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))
    source_item = _build_source_item()
    prepared_document = _build_prepared_document(source_item)

    saved = repository.save(source_item, prepared_document, embedding=_build_embedding())

    assert session.committed == 1
    assert session.closed == 1
    assert saved.document_text == prepared_document.document_text
    assert session.added[0].published_at == source_item.published_at
    _assert_immutable_source_item(saved)
    session.added[0].document_text = "changed after close"
    assert saved.document_text == prepared_document.document_text


def test_get_by_source_and_external_id_returns_immutable_detached_dto() -> None:
    detached_model = DetachableSourceItem(_source_model())
    session = FakeSession([detached_model])

    found = SourceItemRepository(session_factory=FakeSessionFactory([session])).get_by_source_and_external_id(
        "hackernews", "1"
    )

    assert session.closed == 1
    assert found.title == "Cloud automation"
    _assert_immutable_source_item(found)


def test_get_by_dedup_hash_returns_immutable_detached_dto() -> None:
    model = _source_model()
    session = FakeSession([model])

    found = SourceItemRepository(session_factory=FakeSessionFactory([session])).get_by_dedup_hash(
        "hash-1"
    )

    assert session.closed == 1
    _assert_immutable_source_item(found)
    model.title = "changed after close"
    assert found.title == "Cloud automation"


def test_find_all_with_embeddings_maps_orm_models_to_detached_clusterable_documents() -> None:
    model = _source_model(document_id=7, value=0.2)
    session = FakeSession(scalars_results=[[model]])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))

    documents = repository.find_all_with_embeddings()

    assert documents == [
        ClusterableDocument(
            id=7,
            source="hackernews",
            external_id="7",
            document_text="cloud automation",
            embedding=tuple(_build_embedding(0.2)),
        )
    ]
    assert session.closed == 1
    model.document_text = "changed after close"
    assert documents[0].document_text == "cloud automation"


def test_find_similar_orders_by_cosine_distance_and_excludes_null_embeddings() -> None:
    rows = [_source_model(1), _source_model(2)]
    session = FakeSession(scalars_results=[rows])
    repository = SourceItemRepository(session_factory=FakeSessionFactory([session]))

    found = repository.find_similar(_build_embedding(0.5), limit=5)

    assert session.closed == 1
    assert [item.id for item in found] == [1, 2]
    assert all(isinstance(item, PersistedSourceItem) for item in found)
    assert all(not isinstance(item, SourceItemModel) for item in found)
    _assert_immutable_source_item(found[0])
    rows[0].title = "changed after close"
    assert found[0].title == "Cloud automation"
    statement = session.scalars_statements[0]
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "source_items.embedding IS NOT NULL" in compiled_sql
    assert "source_items.embedding <=>" in compiled_sql


def test_find_similar_rejects_invalid_embedding_length() -> None:
    repository = SourceItemRepository(session_factory=FailingSessionFactory())

    with pytest.raises(ValueError, match="exactly 384 values"):
        repository.find_similar(_build_embedding()[:383])


def test_cluster_repository_resolves_source_items_by_document_id_and_returns_detached_result() -> None:
    source_model = _source_model(document_id=7, value=0.2)
    session = FakeSession(scalars_results=[[source_model]])
    cluster = DocumentCluster(cluster_id=4, documents=(_clusterable_document(7, 0.2),))
    label = TopicLabel(cluster_id=4, label="cloud", keywords=("cloud",))

    result = ClusterRepository(session_factory=FakeSessionFactory([session])).save_run(
        [(cluster, label, None)]
    )

    assert result == PersistedClusterRun(
        id=1,
        clusters=(PersistedCluster(id=101, run_id=1, local_cluster_id=4),),
    )
    assert session.closed == 1
    assert isinstance(result.clusters[0], PersistedCluster)
    assert result.clusters[0].local_cluster_id == 4
    statement = session.scalars_statements[0]
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "source_items.id IN" in compiled_sql
    persisted_model = next(model for model in session.added if isinstance(model, ClusterModel))
    assert persisted_model.source_items == [source_model]


def test_cluster_repository_updates_only_within_the_same_run() -> None:
    run = ClusterRunModel(id=11)
    existing = ClusterModel(id=22, run_id=11, local_cluster_id=4)
    source_model = _source_model(document_id=7)
    session = FakeSession(scalar_results=[run, existing], scalars_results=[[source_model]])
    cluster = DocumentCluster(cluster_id=4, documents=(_clusterable_document(7),))
    label = TopicLabel(cluster_id=4, label="updated", keywords=("updated",))

    result = ClusterRepository(session_factory=FakeSessionFactory([session])).save_to_run(
        11, cluster, label, centroid=_build_embedding()
    )

    assert result == PersistedCluster(id=22, run_id=11, local_cluster_id=4)
    assert existing.label == "updated"
    assert existing.source_items == [source_model]


def test_cluster_repository_rejects_empty_cluster_before_opening_session() -> None:
    repository = ClusterRepository(session_factory=FailingSessionFactory())
    cluster = DocumentCluster(cluster_id=1, documents=())
    label = TopicLabel(cluster_id=1, label="empty", keywords=("empty",))

    with pytest.raises(ValueError, match="empty cluster"):
        repository.save(cluster, label)


def test_cluster_repository_rejects_missing_document_ids() -> None:
    session = FakeSession(scalars_results=[[]])
    cluster = DocumentCluster(cluster_id=1, documents=(_clusterable_document(99),))
    label = TopicLabel(cluster_id=1, label="missing", keywords=("missing",))

    with pytest.raises(ValueError, match="do not exist"):
        ClusterRepository(session_factory=FakeSessionFactory([session])).save(cluster, label)

    assert session.rolled_back == 1
    assert session.closed == 1

@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_repository_rejects_non_finite_embedding_before_opening_session(
    invalid_value: float,
) -> None:
    repository = SourceItemRepository(session_factory=FailingSessionFactory())
    source_item = _build_source_item()
    prepared_document = _build_prepared_document(source_item)

    with pytest.raises(ValueError, match="embedding values must be finite"):
        repository.save(source_item, prepared_document, embedding=_build_embedding(invalid_value))


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_find_similar_rejects_non_finite_embedding_before_opening_session(
    invalid_value: float,
) -> None:
    repository = SourceItemRepository(session_factory=FailingSessionFactory())

    with pytest.raises(ValueError, match="embedding values must be finite"):
        repository.find_similar(_build_embedding(invalid_value))


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_cluster_repository_rejects_non_finite_centroid(invalid_value: float) -> None:
    session = FakeSession()
    cluster = DocumentCluster(cluster_id=1, documents=(_clusterable_document(7),))
    label = TopicLabel(cluster_id=1, label="cloud", keywords=("cloud",))

    with pytest.raises(ValueError, match="centroid values must be finite"):
        ClusterRepository(session_factory=FakeSessionFactory([session])).save(
            cluster,
            label,
            centroid=_build_embedding(invalid_value),
        )

    assert session.rolled_back == 1
    assert session.closed == 1


def test_repository_rejects_naive_published_at_before_opening_session() -> None:
    repository = SourceItemRepository(session_factory=FailingSessionFactory())
    source_item = _build_source_item()
    source_item.published_at = datetime(2023, 11, 14, 22, 13, 20)
    prepared_document = _build_prepared_document(source_item)

    with pytest.raises(ValueError, match="published_at must be timezone-aware"):
        repository.save(source_item, prepared_document, embedding=_build_embedding())
