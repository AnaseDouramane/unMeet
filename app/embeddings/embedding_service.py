from collections.abc import Sequence

import numpy as np

from app.config import settings

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model or DEFAULT_EMBEDDING_MODEL
        self._model = None

    def _load_model(self) -> None:
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)

    def encode(self, document_text: str) -> list[float]:
        return self.encode_batch([document_text])[0]

    def encode_batch(self, document_texts: Sequence[str]) -> list[list[float]]:
        if isinstance(document_texts, (str, bytes)):
            raise ValueError("document_texts must be a sequence of texts, not a single string or bytes")

        texts = list(document_texts)
        self._validate_texts(texts)

        self._load_model()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return self._coerce_embeddings(embeddings, expected_count=len(texts))

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> None:
        if not texts:
            raise ValueError("document_text cannot be empty")

        for text in texts:
            if not isinstance(text, str):
                raise TypeError("document_text must be a string")
            if not text.strip():
                raise ValueError("document_text cannot be empty")

    @staticmethod
    def _coerce_embeddings(embeddings: object, expected_count: int) -> list[list[float]]:
        array = np.asarray(embeddings, dtype=float)

        if array.size == 0:
            raise ValueError("embedding output cannot be empty")

        if array.ndim == 1:
            if expected_count != 1:
                raise ValueError("embedding output shape does not match the input batch size")
            array = array.reshape(1, -1)

        if array.ndim != 2:
            raise ValueError("embedding output must be a 1D or 2D array")

        if array.shape[0] != expected_count:
            raise ValueError("embedding output shape does not match the input batch size")

        if array.shape[1] == 0:
            raise ValueError("embedding output cannot be empty")

        return array.tolist()
