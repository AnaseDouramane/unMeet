from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.llm.client import LLMUsage
from app.usage.llm_usage import LlmUsageRepository


def test_totals_group_by_purpose_and_cost_is_unknown_when_unpriced(
    session_factory: sessionmaker[Session],
) -> None:
    priced = LlmUsageRepository(session_factory, input_usd_per_mtok=1.0, output_usd_per_mtok=2.0)
    priced.record(LLMUsage("m", 1_000_000, 500_000, "classification"))  # 1.0 + 1.0
    priced.record(LLMUsage("m", 1_000_000, 0, "classification"))  # 1.0
    priced.record(LLMUsage("m", 100, 10, "cluster_labeling"))
    LlmUsageRepository(session_factory).record(LLMUsage("m", 5, 5, "cluster_labeling"))  # unpriced

    by_purpose = {t.purpose: t for t in priced.totals()}

    classification = by_purpose["classification"]
    assert (classification.calls, classification.prompt_tokens) == (2, 2_000_000)
    assert classification.completion_tokens == 500_000
    assert classification.cost_usd == 3.0
    labeling = by_purpose["cluster_labeling"]
    assert labeling.calls == 2 and labeling.prompt_tokens == 105
    assert labeling.cost_usd is None  # one unpriced call: total is unknown, not understated


def test_since_filters_old_rows(session_factory: sessionmaker[Session]) -> None:
    repository = LlmUsageRepository(session_factory, 1.0, 1.0)
    repository.record(LLMUsage("m", 10, 10, "classification"))
    future = datetime.now(UTC) + timedelta(days=1)
    assert repository.totals(since=future) == ()
    assert repository.totals(since=datetime.now(UTC) - timedelta(days=1))[0].calls == 1
