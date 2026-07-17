from __future__ import annotations

import numpy as np
import pytest

from app.embeddings.embedding_service import EmbeddingService


class FakeSentenceTransformer:
    instances = 0

    def __init__(self, model_name: str) -> None:
        type(self).instances += 1
        self.model_name = model_name
        self.calls: list[tuple[list[str], bool]] = []

    def encode(self, texts: list[str], normalize_embeddings: bool = False) -> np.ndarray:
        self.calls.append((list(texts), normalize_embeddings))
        if len(texts) == 1:
            return np.array([1.0, 2.0, 3.0])
        return np.array(
            [
                [4.0, 5.0, 6.0],
                [7.0, 8.0, 9.0],
            ]
        )


class EmptySentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(self, texts: list[str], normalize_embeddings: bool = False) -> np.ndarray:
        if len(texts) == 1:
            return np.array([])
        return np.array([[]])


class MismatchedSentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(self, texts: list[str], normalize_embeddings: bool = False) -> np.ndarray:
        return np.array([1.0, 2.0, 3.0])


@pytest.mark.parametrize("batch_input", ["abc", b"abc"])
def test_embedding_service_rejects_string_and_bytes_batch_input(
    monkeypatch: pytest.MonkeyPatch,
    batch_input: object,
) -> None:
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeSentenceTransformer)

    service = EmbeddingService(model_name="mock-model")

    with pytest.raises(ValueError, match="single string or bytes"):
        service.encode_batch(batch_input)  # type: ignore[arg-type]


def test_embedding_service_loads_model_once_and_supports_single_and_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSentenceTransformer.instances = 0
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeSentenceTransformer)

    service = EmbeddingService(model_name="mock-model")

    single_embedding = service.encode("First document")
    batch_embeddings = service.encode_batch(["Second document", "Third document"])

    assert FakeSentenceTransformer.instances == 1
    assert service._model is not None
    assert service._model.model_name == "mock-model"
    assert service._model.calls == [
        (["First document"], True),
        (["Second document", "Third document"], True),
    ]
    assert single_embedding == [1.0, 2.0, 3.0]
    assert batch_embeddings == [[4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]


@pytest.mark.parametrize("document_text", ["", "   "])
def test_embedding_service_rejects_empty_text(monkeypatch: pytest.MonkeyPatch, document_text: str) -> None:
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeSentenceTransformer)

    service = EmbeddingService(model_name="mock-model")

    with pytest.raises(ValueError, match="cannot be empty"):
        service.encode(document_text)


def test_embedding_service_rejects_empty_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeSentenceTransformer)

    service = EmbeddingService(model_name="mock-model")

    with pytest.raises(ValueError, match="cannot be empty"):
        service.encode_batch([])


@pytest.mark.parametrize("service_method, arguments", [("encode", ("Hello",)), ("encode_batch", (["Hello"],))])
def test_embedding_service_rejects_empty_output(
    monkeypatch: pytest.MonkeyPatch,
    service_method: str,
    arguments: tuple[object, ...],
) -> None:
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", EmptySentenceTransformer)

    service = EmbeddingService(model_name="mock-model")

    with pytest.raises(ValueError, match="embedding output cannot be empty"):
        getattr(service, service_method)(*arguments)


def test_embedding_service_rejects_mismatched_batch_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", MismatchedSentenceTransformer)

    service = EmbeddingService(model_name="mock-model")

    with pytest.raises(ValueError, match="shape does not match the input batch size"):
        service.encode_batch(["First document", "Second document"])
