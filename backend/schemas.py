"""Pydantic schemas for request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# Version string stored when a user accepts Terms + Privacy at registration (sync with static legal pages).
LEGAL_DOCS_VERSION = "2026-05-01"


# ─── Auth ──────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=40)
    line_id: Optional[str] = Field(default=None, max_length=80)
    xm_id: Optional[str] = Field(default=None, max_length=40)
    account_type: Optional[str] = Field(default=None, max_length=40)
    target_reward: Optional[str] = Field(default=None, max_length=40)
    accept_terms: bool = Field(
        ...,
        description="Must be true — explicit acceptance of Terms and Privacy Policy.",
    )

    @field_validator("accept_terms")
    @classmethod
    def _accept_terms_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("ต้องยอมรับเงื่อนไขการให้บริการและนโยบายความเป็นส่วนตัว")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ForgotPasswordOut(BaseModel):
    ok: bool = True
    message: str = "หากอีเมลนี้มีในระบบ คุณจะได้รับลิงก์รีเซ็ตรหัสผ่านในไม่กี่นาที กรุณาตรวจสอบกล่อง junk / สแปมด้วย"


class RequestResetByIdentityIn(BaseModel):
    """MT ID on file must match; no email is sent. Weaker than inbox proof — use for convenience."""
    email: EmailStr
    xm_id: str = Field(..., min_length=1, max_length=40)


class RequestResetByIdentityOut(BaseModel):
    ok: bool = True
    message: str = ""
    token: Optional[str] = None


class ResetPasswordIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=90)
    new_password: str = Field(..., min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    claimed_placeholder: bool = False
    claimed_lots: float = 0.0


class PreviewClaimOut(BaseModel):
    """Public lookup so the join page can tell a customer
    whether their MT ID already has Lots waiting for them."""
    mt_id: str
    has_placeholder: bool
    total_lots: float = 0.0
    trade_count: int = 0


# ─── User ──────────────────────────────────────────────────────────
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    phone: Optional[str] = None
    line_id: Optional[str] = None
    xm_id: Optional[str] = None
    account_type: Optional[str] = None
    target_reward: Optional[str] = None
    display_handle: Optional[str] = None
    is_admin: bool = False
    created_at: datetime


# ─── Lots ──────────────────────────────────────────────────────────
class LotIn(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=20)
    side: str = Field(..., pattern="^(buy|sell|Buy|Sell|BUY|SELL)$")
    lots: float = Field(..., gt=0, le=1000)


class LotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: str
    lots: float
    traded_at: datetime


# ─── Personal trade journal (not reward Lots) ────────────────────
class TradeJournalIn(BaseModel):
    """Manual entry for self statistics — does not change program Lot totals."""
    symbol: str = Field(..., min_length=2, max_length=20)
    side: str = Field(..., pattern="^(buy|sell|Buy|Sell|BUY|SELL)$")
    lot_size: float = Field(..., gt=0, le=1000, description="ออเดอร์ lot size — บันทึกสำหรับดูรวมเท่านั้น")
    pnl: Optional[float] = Field(default=None, description="กำไร/ขาดทุน: บวกหรือลบได้")
    note: Optional[str] = Field(default=None, max_length=200)
    traded_at: Optional[datetime] = None


class TradeJournalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: str
    lot_size: float
    pnl: Optional[float] = None
    note: Optional[str] = None
    traded_at: datetime


class TradeJournalSummaryOut(BaseModel):
    total_orders: int
    orders_with_pnl: int
    total_pnl: float
    wins: int
    losses: int
    break_even: int


# ─── Tier / Progress ───────────────────────────────────────────────
class TierInfo(BaseModel):
    rank: int
    key: str
    name: str
    lots_required: int
    reward: str
    value_thb: str


class ProgressOut(BaseModel):
    total_lots: float
    monthly_lots: float
    current_tier: TierInfo
    next_tier: Optional[TierInfo]
    lots_to_next: float
    progress_pct: float
    rewards_value_thb: int


# ─── Claim ─────────────────────────────────────────────────────────
class ClaimIn(BaseModel):
    tier_key: str


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tier: str
    reward_name: str
    status: str
    claimed_at: datetime


# ─── Leaderboard ───────────────────────────────────────────────────
class LeaderRow(BaseModel):
    rank: int
    handle: str
    tier_name: str
    tier_key: str
    total_lots: float


# ─── Admin / CSV import ────────────────────────────────────────────
class CsvPreviewMtSummary(BaseModel):
    mt_id: str
    matched: bool
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    trade_count: int
    new_trade_count: int
    lots_sum: float
    new_lots_sum: float


class CsvPreviewOut(BaseModel):
    filename: str
    file_hash: str
    already_imported: bool = False
    total_rows: int
    parsed_rows: int
    error_rows: int
    duplicate_rows: int           # rows already in DB by external_trade_id
    new_rows: int                 # rows that would be inserted
    matched_users: int
    unmatched_mt_ids: list[str]
    total_lots_in_file: float
    new_lots_to_add: float
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    by_mt_id: list[CsvPreviewMtSummary]
    sample_errors: list[dict] = []


class CsvImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_hash: str
    total_rows: int
    imported_rows: int
    skipped_duplicates: int
    unmatched_rows: int
    matched_users: int
    total_lots_added: float
    notes: Optional[str] = None
    created_at: datetime


class AdminUserRow(BaseModel):
    id: int
    name: str
    email: str
    xm_id: Optional[str] = None
    display_handle: Optional[str] = None
    total_lots: float
    is_admin: bool
    merge_message: Optional[str] = None


class AdminUserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    xm_id: Optional[str] = Field(default=None, max_length=40)
    display_handle: Optional[str] = Field(default=None, max_length=40)
    is_admin: Optional[bool] = None
    new_password: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="New login password (bcrypt; cannot read old password).",
    )


class CreatePlaceholdersIn(BaseModel):
    mt_ids: list[str] = Field(..., min_length=1, max_length=200)
    name_prefix: str = Field(default="Client", max_length=40)


class CreatePlaceholdersOut(BaseModel):
    created: list[AdminUserRow]
    skipped: list[str]   # MT IDs already in use
