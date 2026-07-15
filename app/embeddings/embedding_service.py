from collections.abc import Sequence


class EmbeddingService:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)

    def encode(self, texts: Sequence[str]):
        if self._model is None:
            self.load()
        return self._model.encode(list(texts), normalize_embeddings=True)
