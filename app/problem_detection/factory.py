from app.config import Settings
from app.problem_detection.llm import OpenAICompatibleSignalClassifier
from app.problem_detection.qwen3 import Qwen3ProblemClassifier
from app.problem_detection.schemas import ProblemClassifier
from app.usage.llm_usage import LlmUsageRepository

SUPPORTED_CLASSIFIER_BACKENDS = frozenset({"qwen3", "llm"})


def build_problem_classifier(settings: Settings) -> ProblemClassifier:
    """Build the classifier selected by ``CLASSIFIER_BACKEND``.

    ``qwen3`` runs a small local model (no API key, binary output only). ``llm`` calls an
    OpenAI-compatible API and also extracts intent, pain quote, products and severity.
    """
    backend = settings.classifier_backend
    if backend == "qwen3":
        return Qwen3ProblemClassifier()
    if backend == "llm":
        if not settings.llm_model:
            raise ValueError("LLM_MODEL must be set when CLASSIFIER_BACKEND=llm")
        return OpenAICompatibleSignalClassifier(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            use_json_schema=settings.llm_use_json_schema,
            usage_sink=build_usage_sink(settings),
        )
    raise ValueError(
        f"Unknown CLASSIFIER_BACKEND {backend!r}; "
        f"expected one of {sorted(SUPPORTED_CLASSIFIER_BACKENDS)}"
    )


def build_usage_sink(settings: Settings):
    """Persist token usage and estimated cost unless ``LLM_USAGE_TRACKING`` is off."""
    if not getattr(settings, "llm_usage_tracking", False):
        return None
    return LlmUsageRepository(
        input_usd_per_mtok=getattr(settings, "llm_input_usd_per_mtok", None),
        output_usd_per_mtok=getattr(settings, "llm_output_usd_per_mtok", None),
    ).record
