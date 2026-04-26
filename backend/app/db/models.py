from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, BigInteger, Float, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base

class StravaToken(Base):
    __tablename__ = "strava_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Strava activity id
    athlete_id: Mapped[int] = mapped_column(BigInteger, index=True)

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    sport_type: Mapped[str | None] = mapped_column(String, nullable=True)

    start_date: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    moving_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    average_speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)

    average_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_heartrate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    private: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

class ActivityStream(Base):
    """
    Stores Strava activity streams as a single JSONB blob per activity (key_by_type=true).
    This is deliberate: fast, simple, re-computable, and avoids enormous row counts.
    """
    __tablename__ = "activity_streams"

    activity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(BigInteger, index=True)

    fetched_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Which stream keys we requested/received (e.g. ["time","distance","altitude","heartrate",...])
    keys: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Raw response from Strava streams endpoint (dict of arrays when key_by_type=true)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

class ActivityMetric(Base):
    __tablename__ = "activity_metrics"

    activity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(BigInteger, index=True)

    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    moving_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)

    avg_pace_s_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_rate_m_per_h: Mapped[float | None] = mapped_column(Float, nullable=True)

    efficiency_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
