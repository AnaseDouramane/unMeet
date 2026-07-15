from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SourceItemModel(Base):
    __tablename__ = "source_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
