import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

# Load variables from a local .env before any setting is read. Variables already present in
# the process environment take precedence, so deployments and tests keep full control.
load_dotenv(find_dotenv(usecwd=True), override=False)

_HACKERNEWS_SUPPORTED_FEEDS = frozenset({"topstories", "newstories", "beststories", "askstories"})


def _reddit_subreddits() -> tuple[str, ...]:
    return tuple(
        subreddit.strip()
        for subreddit in os.getenv("REDDIT_SUBREDDITS", "").split(",")
        if subreddit.strip()
    )


def _github_repositories() -> tuple[str, ...]:
    return tuple(
        repository.strip()
        for repository in os.getenv("GITHUB_REPOSITORIES", "").split(",")
        if repository.strip()
    )


def _enabled_sources() -> tuple[str, ...]:
    return tuple(
        source.strip().lower()
        for source in os.getenv("INGESTION_SOURCES", "hackernews").split(",")
        if source.strip()
    )


def _hackernews_searches() -> tuple[str, ...]:
    """Raw ``tag`` or ``tag:query`` specs separated by ``;`` (parsed by the connector factory)."""
    return tuple(
        spec.strip()
        for spec in os.getenv("HACKERNEWS_SEARCHES", "ask_hn").split(";")
        if spec.strip()
    )


def _hackernews_feeds() -> tuple[str, ...]:
    normalized_feeds: list[str] = []
    seen_feeds: set[str] = set()
    for feed in os.getenv("HACKERNEWS_FEEDS", "topstories,newstories,beststories").split(","):
        if not feed.strip():
            raise ValueError("Hacker News feed names must be non-empty strings")
        normalized_feed = feed.strip().lower()
        if normalized_feed not in _HACKERNEWS_SUPPORTED_FEEDS:
            raise ValueError(f"Unknown Hacker News feed: {normalized_feed}")
        if normalized_feed in seen_feeds:
            raise ValueError(f"Duplicate Hacker News feed: {normalized_feed}")
        seen_feeds.add(normalized_feed)
        normalized_feeds.append(normalized_feed)
    return tuple(normalized_feeds)


def _positive_integer_setting(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _boolean_setting(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _ingestion_fail_fast() -> bool:
    return os.getenv("INGESTION_FAIL_FAST", "true").strip().lower() in {"1", "true", "yes"}


def _api_cors_origins() -> tuple[str, ...]:
    return tuple(
        origin.strip()
        for origin in os.getenv(
            "API_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    )


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("UNMEET_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/unmeet",
    )
    stackexchange_site: str = os.getenv("STACKEXCHANGE_SITE", "stackoverflow")
    stackexchange_queries: tuple[str, ...] = tuple(
        query.strip() for query in os.getenv("STACKEXCHANGE_QUERIES", "").split(";") if query.strip()
    )
    stackexchange_key: str | None = os.getenv("STACKEXCHANGE_KEY") or None
    stackexchange_limit: int = _positive_integer_setting("STACKEXCHANGE_LIMIT", 200)
    reddit_client_id: str | None = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "unMeet/0.1")
    reddit_subreddits: tuple[str, ...] = _reddit_subreddits()
    reddit_limit: int = int(os.getenv("REDDIT_LIMIT", "100"))
    reddit_sort: str = os.getenv("REDDIT_SORT", "new")
    hackernews_feeds: tuple[str, ...] = _hackernews_feeds()
    hackernews_limit: int = _positive_integer_setting("HACKERNEWS_LIMIT", 500)
    hackernews_max_workers: int = _positive_integer_setting("HACKERNEWS_MAX_WORKERS", 16)
    hackernews_searches: tuple[str, ...] = _hackernews_searches()
    hackernews_search_limit: int = _positive_integer_setting("HACKERNEWS_SEARCH_LIMIT", 300)
    hackernews_search_lookback_seconds: int = _positive_integer_setting(
        "HACKERNEWS_SEARCH_LOOKBACK_SECONDS", 3600
    )
    hackernews_include_comments: bool = _boolean_setting("HACKERNEWS_INCLUDE_COMMENTS", True)
    hackernews_max_comments_per_story: int = _positive_integer_setting(
        "HACKERNEWS_MAX_COMMENTS_PER_STORY", 20
    )
    enabled_sources: tuple[str, ...] = _enabled_sources()
    ingestion_fail_fast: bool = _ingestion_fail_fast()
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_repositories: tuple[str, ...] = _github_repositories()
    github_issues_limit: int = _positive_integer_setting("GITHUB_ISSUES_LIMIT", 100)
    github_issues_state: str = os.getenv("GITHUB_ISSUES_STATE", "open")
    github_issues_sort: str = os.getenv("GITHUB_ISSUES_SORT", "updated")
    classifier_backend: str = os.getenv("CLASSIFIER_BACKEND", "qwen3").strip().lower()
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    llm_model: str | None = os.getenv("LLM_MODEL") or None
    llm_input_usd_per_mtok: float | None = (
        float(os.environ["LLM_INPUT_USD_PER_MTOK"]) if os.getenv("LLM_INPUT_USD_PER_MTOK") else None
    )
    llm_output_usd_per_mtok: float | None = (
        float(os.environ["LLM_OUTPUT_USD_PER_MTOK"]) if os.getenv("LLM_OUTPUT_USD_PER_MTOK") else None
    )
    llm_usage_tracking: bool = _boolean_setting("LLM_USAGE_TRACKING", True)
    retention_non_signal_days: int = _positive_integer_setting("RETENTION_NON_SIGNAL_DAYS", 30)
    retention_signal_days: int = _positive_integer_setting("RETENTION_SIGNAL_DAYS", 365)
    ingestion_stale_after_seconds: int = _positive_integer_setting(
        "INGESTION_STALE_AFTER_SECONDS", 21600
    )
    privacy_contact_email: str | None = os.getenv("PRIVACY_CONTACT_EMAIL") or None
    auth_jwt_secret: str | None = os.getenv("AUTH_JWT_SECRET") or None
    auth_jwks_url: str | None = os.getenv("AUTH_JWKS_URL") or None
    auth_jwt_issuer: str | None = os.getenv("AUTH_JWT_ISSUER") or None
    auth_jwt_audience: str | None = os.getenv("AUTH_JWT_AUDIENCE") or None
    smtp_host: str | None = os.getenv("SMTP_HOST") or None
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME") or None
    smtp_password: str | None = os.getenv("SMTP_PASSWORD") or None
    smtp_from: str | None = os.getenv("SMTP_FROM") or None
    smtp_starttls: bool = _boolean_setting("SMTP_STARTTLS", True)
    labeling_backend: str = os.getenv("LABELING_BACKEND", "keywords").strip().lower()
    classification_batch_size: int = _positive_integer_setting("CLASSIFICATION_BATCH_SIZE", 1)
    poll_interval_seconds: int = _positive_integer_setting("POLL_INTERVAL_SECONDS", 600)
    poll_max_backoff_seconds: int = _positive_integer_setting("POLL_MAX_BACKOFF_SECONDS", 3600)
    poll_stall_after_seconds: int = _positive_integer_setting("POLL_STALL_AFTER_SECONDS", 10800)
    topic_gate_enabled: bool = _boolean_setting("TOPIC_GATE_ENABLED", True)
    classification_workers: int = _positive_integer_setting("CLASSIFICATION_WORKERS", 8)
    llm_use_json_schema: bool = _boolean_setting("LLM_USE_JSON_SCHEMA", True)
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )
    api_title: str = os.getenv("API_TITLE", "unMeet API")
    api_version: str = os.getenv("API_VERSION", "0.1.0")
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_cors_origins: tuple[str, ...] = _api_cors_origins()
    api_key: str | None = os.getenv("UNMEET_API_KEY") or None
    rate_limit_read_per_minute: int = int(os.getenv("RATE_LIMIT_READ_PER_MINUTE", "120"))
    rate_limit_write_per_minute: int = int(os.getenv("RATE_LIMIT_WRITE_PER_MINUTE", "30"))
    trust_proxy_headers: bool = _boolean_setting("TRUST_PROXY_HEADERS", False)


settings = Settings()
