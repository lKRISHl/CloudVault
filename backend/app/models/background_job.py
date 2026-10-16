from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BackgroundJob(Base):
    """Operator-only maintenance state; queue messages never contain user content."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(
            "name IN ('email', 'storage', 'previews', 'scans')", name="ck_background_job_name"
        ),
        CheckConstraint("runs >= 0 AND failures >= 0", name="ck_background_job_counts"),
    )

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    lease_id: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cursor: Mapped[dict | None] = mapped_column(JSON)
