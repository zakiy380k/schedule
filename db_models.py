from sqlalchemy import JSON, CheckConstraint, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TeacherDB(Base):
    __tablename__ = "teachers"

    __table_args__ = (
        CheckConstraint(
            "max_lessons_per_day BETWEEN 1 AND 4", name="teacher_daily_limit"
        ),
        CheckConstraint("annual_load_hours >= 0", name="teacher_annual_load"),
        CheckConstraint("employment_rate > 0", name="teacher_employment_rate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    methodical_days: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list
    )

    max_lessons_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    employment_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    annual_load_hours: Mapped[float] = mapped_column(
        Float, nullable=False, default=1080.0
    )


class DataRecord(Base):
    """Editable source rows; section and ID form a stable composite key."""

    __tablename__ = "data_records"
    section: Mapped[str] = mapped_column(String(30), primary_key=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class DataSection(Base):
    """Tracks imports, including intentionally empty datasets."""

    __tablename__ = "data_sections"
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
