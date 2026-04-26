from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, BigInteger

from app.db.session import Base

class StravaToken(Base):
    __tablename__ = "strava_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
