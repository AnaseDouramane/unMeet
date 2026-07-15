from dataclasses import dataclass
import os


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
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )


settings = Settings()
