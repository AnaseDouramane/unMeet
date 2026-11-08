import pytest

from app.topics.schemas import TopicDefinition, validate_webhook_url


def test_a_topic_needs_at_least_one_criterion() -> None:
    with pytest.raises(ValueError, match="description, intents or products"):
        TopicDefinition(name="Empty")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": " "}, "name"),
        ({"intents": ("none",)}, "intents"),
        ({"min_severity": 0}, "min_severity"),
        ({"max_distance": 0}, "max_distance"),
    ],
)
def test_invalid_topics_are_rejected(overrides, message: str) -> None:
    values = {"name": "Topic", "description": "slow CI pipelines"}
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        TopicDefinition(**values)


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/x",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://10.0.0.8/x",
        "https://[::1]/x",
        "https://metadata.internal/x",
        "ftp://example.com",
        "not a url",
    ],
)
def test_unsafe_webhook_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="webhook_url"):
        validate_webhook_url(url)


def test_public_https_webhooks_are_accepted() -> None:
    validate_webhook_url("https://api.clay.com/v3/sources/webhook/pull-in-data-from-a-webhook-1")
    validate_webhook_url("https://hooks.zapier.com/hooks/catch/1/abc/")


def test_keywords_are_validated() -> None:
    from app.topics.schemas import MAX_KEYWORDS, TopicDefinition

    ok = TopicDefinition(
        name="t", description="d", keywords=("looking for a tool", "alternative to x")
    )
    assert ok.keywords == ("looking for a tool", "alternative to x")
    for bad in (
        ("",),
        ("  ",),
        ('say "hi"',),
        ("x" * 81,),
        tuple(f"k{i}" for i in range(MAX_KEYWORDS + 1)),
    ):
        with pytest.raises(ValueError):
            TopicDefinition(name="t", description="d", keywords=bad)
