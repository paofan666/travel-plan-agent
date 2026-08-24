from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Base


def _utc_now() -> datetime:
    """Return naive UTC for the existing SQLite DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class TripRecord(Base):
    """当前版本使用的最小行程表。"""

    __tablename__ = "trip_records"

    # 数据库内部主键
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 业务侧使用的 itinerary 标识
    trip_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    destination: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    # 完整 itinerary 的 JSON 字符串
    itinerary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utc_now,
        server_default=func.now(),
        onupdate=_utc_now,
    )
