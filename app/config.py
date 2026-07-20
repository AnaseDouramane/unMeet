from dataclasses import dataclass
import os


def _reddit_subreddits() -> tuple[str, ...]:
    return tuple(
        subreddit.strip()
        for subreddit in os.getenv("REDDIT_SUBREDDITS", "").split(",")
        if subreddit.strip()
    )


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("UNMEET_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/unmeet",
    )
    stackexchange_site: str = os.getenv("STACKEXCHANGE_SITE", "stackoverflow")
    reddit_client_id: str | None = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "unMeet/0.1")
    reddit_subreddits: tuple[str, ...] = _reddit_subreddits()
    reddit_limit: int = int(os.getenv("REDDIT_LIMIT", "100"))
    reddit_sort: str = os.getenv("REDDIT_SORT", "new")
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )


settings = Settings()
