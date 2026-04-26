"""Database models for The Lot Legends."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    line_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    xm_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    account_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_reward: Mapped[str | None] = mapped_column(String(40), nullable=True)

    is_admin: Mapped[bool] = mapped_column(default=False)
    display_handle: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lots: Mapped[list["LotEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    claims: Mapped[list["RewardClaim"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LotEntry(Base):
    """One trade entry contributing to a user's lot total."""
    __tablename__ = "lot_entries"
    __table_args__ = (
        UniqueConstraint("source", "external_trade_id", name="uq_lotentry_source_extid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy/sell
    lots: Mapped[float] = mapped_column(Float, nullable=False)
    traded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # ── Provenance ──
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual", index=True)
    # 'manual' | 'seed' | 'partner_csv'
    external_trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    account_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("csv_imports.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user: Mapped[User] = relationship(back_populates="lots")
    import_batch: Mapped["CsvImport | None"] = relationship(back_populates="entries")


class CsvImport(Base):
    """One Partner-CSV import job — used for audit + dedup + rollback."""
    __tablename__ = "csv_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(160), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    skipped_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_rows: Mapped[int] = mapped_column(Integer, default=0)
    matched_users: Mapped[int] = mapped_column(Integer, default=0)
    total_lots_added: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    entries: Mapped[list["LotEntry"]] = relationship(back_populates="import_batch")


class RewardClaim(Base):
    """When a user claims a reward at a tier they reached."""
    __tablename__ = "reward_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    reward_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|shipped|delivered
    claimed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="claims")
