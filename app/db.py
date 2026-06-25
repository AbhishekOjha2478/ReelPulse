import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class RunLog(Base):
    __tablename__ = "run_logs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")  # running | completed | failed
    quota_units_used = Column(Integer, default=0)
    notes = Column(Text, default="")


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, nullable=True)
    phrase = Column(String, nullable=False)
    source = Column(String, default="")  # youtube_trending | google_trends
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    video_id = Column(String, nullable=False, unique=True)
    keyword = Column(String, nullable=False)
    title = Column(String, default="")
    channel_title = Column(String, default="")
    channel_id = Column(String, default="")
    video_url = Column(String, default="")
    license = Column(String, default="")  # must be "creativeCommon"
    license_verified_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    used = Column(Boolean, default=False)
    rejected_reason = Column(String, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, nullable=True)
    kind = Column(String, default="short")  # short | compilation
    youtube_video_id = Column(String, default="")
    title = Column(String, default="")
    description = Column(Text, default="")
    source_candidate_ids = Column(String, default="")  # comma-separated Candidate.id list
    privacy_status = Column(String, default="private")
    dry_run = Column(Boolean, default=True)
    status = Column(String, default="pending")  # pending | uploaded | failed | skipped
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class BlockedChannel(Base):
    __tablename__ = "blocked_channels"

    id = Column(Integer, primary_key=True)
    channel_id = Column(String, nullable=False, unique=True)
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PipelineState(Base):
    """Single-row table holding the circuit-breaker / pause flag."""

    __tablename__ = "pipeline_state"

    id = Column(Integer, primary_key=True)
    paused = Column(Boolean, default=False)
    pause_reason = Column(Text, default="")


def init_db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        if session.query(PipelineState).first() is None:
            session.add(PipelineState(paused=False))
            session.commit()
    finally:
        session.close()


def get_session():
    return SessionLocal()
