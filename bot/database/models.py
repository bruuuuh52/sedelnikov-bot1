from datetime import datetime, timezone
from sqlalchemy import (
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class ScreeningStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class Candidate(Base):
    __tablename__ = "candidates"

    # PK: Integer работает с автоинкрементом в SQLite
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # telegram_id: BigInteger для поддержки больших ID (Telegram ID > 2^31)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    screenings: Mapped[list["Screening"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Candidate(id={self.id}, tg_id={self.telegram_id}, username={self.username!r})>"


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_min_years: Mapped[int | None] = mapped_column(nullable=True)
    salary_min: Mapped[int | None] = mapped_column(nullable=True)
    salary_max: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    screenings: Mapped[list["Screening"]] = relationship(back_populates="vacancy")

    def __repr__(self) -> str:
        return f"<Vacancy(id={self.id}, title={self.title!r})>"


class Screening(Base):
    __tablename__ = "screenings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id", ondelete="SET NULL"), nullable=True, index=True)

    experience_years: Mapped[int | None] = mapped_column(nullable=True)
    stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_expectation: Mapped[int | None] = mapped_column(nullable=True)
    relocation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    free_evenings: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ScreeningStatus] = mapped_column(
        SQLEnum(ScreeningStatus), default=ScreeningStatus.IN_PROGRESS, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="screenings")
    vacancy: Mapped["Vacancy"] = relationship(back_populates="screenings")

    __table_args__ = (
        UniqueConstraint("candidate_id", "vacancy_id", name="uq_candidate_vacancy"),
    )

    def __repr__(self) -> str:
        return f"<Screening(id={self.id}, candidate_id={self.candidate_id}, status={self.status.value})>"