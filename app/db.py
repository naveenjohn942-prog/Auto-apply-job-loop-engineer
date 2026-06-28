from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, JSON, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    target_role: Mapped[str] = mapped_column(String)
    skills: Mapped[list] = mapped_column(JSON)
    experience: Mapped[list] = mapped_column(JSON)
    education: Mapped[list] = mapped_column(JSON)
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job_postings: Mapped[list[JobPosting]] = relationship(back_populates="candidate_profile")


class JobPosting(Base):
    __tablename__ = "job_postings"

    __table_args__ = (UniqueConstraint("adzuna_id", "candidate_profile_id", name="uq_job_adzuna_candidate"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    adzuna_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    company: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[int] = mapped_column(Integer)
    reasoning: Mapped[str] = mapped_column(String)
    skill_matches: Mapped[list] = mapped_column(JSON)
    skill_gaps: Mapped[list] = mapped_column(JSON)
    candidate_profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="job_postings")
    application_records: Mapped[list[ApplicationRecord]] = relationship(back_populates="job_posting")


class ApplicationRecord(Base):
    __tablename__ = "application_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_posting_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"), nullable=True)
    candidate_profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    # pending → emailed → failed
    status: Mapped[str] = mapped_column(String, default="pending")
    recruiter_email: Mapped[str | None] = mapped_column(String, nullable=True)
    email_draft: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job_posting: Mapped[JobPosting] = relationship(back_populates="application_records")
