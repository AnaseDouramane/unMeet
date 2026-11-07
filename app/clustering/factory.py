from app.clustering.llm_labeling import LLMTopicLabelingService
from app.clustering.topic_labeling import TopicLabelingService
from app.config import Settings
from app.llm.client import ChatCompletionsClient


def build_cluster_labeler(settings: Settings) -> TopicLabelingService | LLMTopicLabelingService:
    """``LABELING_BACKEND=llm`` writes problem statements; ``keywords`` uses TF-IDF only."""
    backend = settings.labeling_backend
    if backend == "keywords":
        return TopicLabelingService()
    if backend == "llm":
        if not settings.llm_model:
            raise ValueError("LLM_MODEL must be set when LABELING_BACKEND=llm")
        client = ChatCompletionsClient(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )
        return LLMTopicLabelingService(client)
    raise ValueError(f"Unknown LABELING_BACKEND {backend!r}; expected 'keywords' or 'llm'")
