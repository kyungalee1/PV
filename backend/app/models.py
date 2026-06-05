import json
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CaseRecord(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collection_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ae_name: Mapped[str] = mapped_column(String(500), default="")
    is_sae: Mapped[bool] = mapped_column(Boolean, default=False)
    assignee: Mapped[str] = mapped_column(String(120), default="")
    partner_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(80), default="")
    source_file: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    cioms_json: Mapped[str] = mapped_column(Text, default="{}")
    pdf_path: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def cioms_data(self) -> dict:
        try:
            return json.loads(self.cioms_json or "{}")
        except json.JSONDecodeError:
            return {}
