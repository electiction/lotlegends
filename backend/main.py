"""The Lot Legends — FastAPI application.

Serves both the static frontend (index/dashboard/join/login) and the JSON API
under /api/*. SQLite is used for local dev; Postgres in production.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from . import schemas
from .auth import (
    create_access_token,
    get_current_admin,
    get_current_user,
    hash_password,
    verify_password,
)
from .csv_parser import ParseReport, parse_csv_bytes
from .database import SessionLocal, get_db, init_db
from .models import CsvImport, LotEntry, RewardClaim, TradeJournal, User

log = logging.getLogger("lotlegends")
logging.basicConfig(
    level=os.getenv("LOTLEGENDS_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# ─── Tier ladder (single source of truth) ──────────────────────────
TIERS: list[dict] = [
    {"rank": 0, "key": "novice",   "name": "Novice",   "lots_required": 0,    "reward": "—",                                        "value_thb": "—"},
    {"rank": 1, "key": "starter",  "name": "Starter",  "lots_required": 10,   "reward": "เสื้อยืด · หมวก · สติกเกอร์เซต",                "value_thb": "300–500"},
    {"rank": 2, "key": "bronze",   "name": "Bronze",   "lots_required": 30,   "reward": "กระเป๋าเป้ / Power Bank 10,000mAh",         "value_thb": "800–1,200"},
    {"rank": 3, "key": "silver",   "name": "Silver",   "lots_required": 70,   "reward": "หูฟังบลูทูธ Soundcore / JBL",                "value_thb": "1,500–2,500"},
    {"rank": 4, "key": "gold",     "name": "Gold",     "lots_required": 150,  "reward": "Apple Watch SE / Galaxy Watch",            "value_thb": "8,000–10,000"},
    {"rank": 5, "key": "platinum", "name": "Platinum", "lots_required": 300,  "reward": "iPad (Gen 10) / AirPods Pro 2",            "value_thb": "15,000–20,000"},
    {"rank": 6, "key": "diamond",  "name": "Diamond",  "lots_required": 500,  "reward": "MacBook Air M3 / iPhone 16",               "value_thb": "35,000–45,000"},
    {"rank": 7, "key": "master",   "name": "Master",   "lots_required": 700,  "reward": "iPhone 17 Pro Max",                        "value_thb": "55,000"},
    {"rank": 8, "key": "legend",   "name": "Legend",   "lots_required": 1000, "reward": "ทองคำ 1 บาท / Trip ต่างประเทศ",             "value_thb": "60,000+"},
]


def tier_for_lots(total_lots: float) -> dict:
    """Return the highest tier the user has reached."""
    current = TIERS[0]
    for t in TIERS:
        if total_lots >= t["lots_required"]:
            current = t
        else:
            break
    return current


def next_tier(total_lots: float) -> Optional[dict]:
    for t in TIERS:
        if total_lots < t["lots_required"]:
            return t
    return None


# ─── App ───────────────────────────────────────────────────────────
app = FastAPI(title="The Lot Legends API", version="0.1.0")


def _resolve_cors_origins() -> list[str]:
    raw = os.getenv("LOTLEGENDS_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


_origins = _resolve_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],  # browsers reject "*" with credentials
    allow_methods=["*"],
    allow_headers=["*"],
)


def _bootstrap_admin() -> None:
    """Create / promote the bootstrap admin defined by env vars.

    Used so a freshly-deployed instance has at least one admin without needing
    SSH access. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD on
    Render and the user is created (or promoted) on the next startup.
    """
    email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or ""
    if not email or not password:
        return

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user:
            if not user.is_admin:
                user.is_admin = True
                db.commit()
                log.info("Promoted existing user %s to admin", email)
            return
        user = User(
            name=os.getenv("BOOTSTRAP_ADMIN_NAME", "Admin"),
            email=email,
            password_hash=hash_password(password),
            is_admin=True,
            display_handle="Admin",
            account_type="Standard",
        )
        db.add(user)
        db.commit()
        log.info("Bootstrap admin created: %s", email)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        _bootstrap_admin()
    except Exception as ex:  # noqa: BLE001
        log.exception("Bootstrap admin failed: %s", ex)


# ─── Health ────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "The Lot Legends"}


@app.get("/api/tiers", response_model=list[schemas.TierInfo])
def get_tiers():
    return [t for t in TIERS if t["rank"] > 0]


# ─── Auth ──────────────────────────────────────────────────────────
PLACEHOLDER_EMAIL_DOMAIN = "@placeholder.lotlegends.local"


def _is_placeholder(user: User) -> bool:
    return bool(user.email and user.email.endswith(PLACEHOLDER_EMAIL_DOMAIN))


@app.get("/api/auth/preview-claim/{mt_id}", response_model=schemas.PreviewClaimOut)
def preview_claim(mt_id: str, db: Session = Depends(get_db)):
    """Public lookup: does this MT ID have unclaimed Lots waiting?

    Used by the join page so a customer who's already had trades imported
    by the partner can see "you have X Lots ready" before they finish signing up.

    The endpoint returns only aggregate numbers — no name / email — so it's safe
    to expose publicly.
    """
    mt = (mt_id or "").strip()
    if not mt:
        raise HTTPException(status_code=400, detail="ระบุ MT ID")

    placeholder = (
        db.query(User)
        .filter(User.xm_id == mt, User.email.like(f"%{PLACEHOLDER_EMAIL_DOMAIN}"))
        .first()
    )
    if not placeholder:
        return schemas.PreviewClaimOut(mt_id=mt, has_placeholder=False)

    total = db.query(func.coalesce(func.sum(LotEntry.lots), 0.0)).filter(
        LotEntry.user_id == placeholder.id
    ).scalar() or 0.0
    count = db.query(func.count(LotEntry.id)).filter(
        LotEntry.user_id == placeholder.id
    ).scalar() or 0

    return schemas.PreviewClaimOut(
        mt_id=mt,
        has_placeholder=True,
        total_lots=round(float(total), 2),
        trade_count=int(count),
    )


@app.post("/api/auth/register", response_model=schemas.TokenOut)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    new_email = payload.email.lower().strip()
    new_xm = (payload.xm_id or "").strip() or None

    # If an MT ID is provided AND a placeholder exists for it, claim that
    # placeholder instead of creating a brand-new user. This is how a customer
    # whose trades were imported by the partner takes ownership of their Lots.
    placeholder: Optional[User] = None
    if new_xm:
        placeholder = (
            db.query(User)
            .filter(
                User.xm_id == new_xm,
                User.email.like(f"%{PLACEHOLDER_EMAIL_DOMAIN}"),
            )
            .first()
        )

    if placeholder:
        clash = db.query(User).filter(
            User.email == new_email, User.id != placeholder.id
        ).first()
        if clash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="อีเมลนี้ถูกใช้งานแล้ว")

        placeholder.name = payload.name.strip()
        placeholder.email = new_email
        placeholder.password_hash = hash_password(payload.password)
        placeholder.phone = payload.phone
        placeholder.line_id = payload.line_id
        placeholder.account_type = payload.account_type or placeholder.account_type
        placeholder.target_reward = payload.target_reward
        placeholder.display_handle = _generate_handle(new_email)
        db.commit()
        db.refresh(placeholder)

        total = db.query(func.coalesce(func.sum(LotEntry.lots), 0.0)).filter(
            LotEntry.user_id == placeholder.id
        ).scalar() or 0.0

        return schemas.TokenOut(
            access_token=create_access_token(placeholder.id),
            claimed_placeholder=True,
            claimed_lots=round(float(total), 2),
        )

    existing = db.query(User).filter(User.email == new_email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="อีเมลนี้ถูกใช้งานแล้ว")

    if new_xm:
        xm_clash = db.query(User).filter(User.xm_id == new_xm).first()
        if xm_clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="MT ID นี้ถูกใช้งานโดยสมาชิกอื่นแล้ว",
            )

    handle = _generate_handle(new_email)
    user = User(
        name=payload.name.strip(),
        email=new_email,
        password_hash=hash_password(payload.password),
        phone=payload.phone,
        line_id=payload.line_id,
        xm_id=new_xm,
        account_type=payload.account_type,
        target_reward=payload.target_reward,
        display_handle=handle,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.TokenOut(access_token=create_access_token(user.id))


@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return schemas.TokenOut(access_token=create_access_token(user.id))


# ─── Me / progress ─────────────────────────────────────────────────
@app.get("/api/me", response_model=schemas.UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@app.get("/api/me/progress", response_model=schemas.ProgressOut)
def me_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total = db.query(func.coalesce(func.sum(LotEntry.lots), 0.0)).filter(LotEntry.user_id == user.id).scalar() or 0.0

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly = (
        db.query(func.coalesce(func.sum(LotEntry.lots), 0.0))
        .filter(LotEntry.user_id == user.id, LotEntry.traded_at >= month_start)
        .scalar()
        or 0.0
    )

    cur = tier_for_lots(total)
    nxt = next_tier(total)
    lots_to_next = max(0.0, nxt["lots_required"] - total) if nxt else 0.0
    pct = 0.0
    if nxt:
        span = nxt["lots_required"] - cur["lots_required"]
        pct = round(((total - cur["lots_required"]) / span) * 100, 2) if span > 0 else 0.0
    else:
        pct = 100.0

    rewards_value = _value_estimate(cur["value_thb"])

    return schemas.ProgressOut(
        total_lots=round(total, 2),
        monthly_lots=round(monthly, 2),
        current_tier=cur,
        next_tier=nxt,
        lots_to_next=round(lots_to_next, 2),
        progress_pct=pct,
        rewards_value_thb=rewards_value,
    )


# ─── Lots ──────────────────────────────────────────────────────────
@app.get("/api/me/lots", response_model=list[schemas.LotOut])
def list_my_lots(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(LotEntry)
        .filter(LotEntry.user_id == user.id)
        .order_by(desc(LotEntry.traded_at))
        .limit(min(limit, 200))
        .all()
    )
    return rows


@app.post("/api/me/lots", response_model=schemas.LotOut, status_code=201)
def add_my_lot(
    payload: schemas.LotIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Legacy: add a LotEntry (counts toward reward program).

    Prefer /api/me/trade-journal for user-facing manual logs — that table does
    not change reward Lot totals. Kept for API compatibility / admin tooling.
    """
    entry = LotEntry(
        user_id=user.id,
        symbol=payload.symbol.upper(),
        side=payload.side.lower(),
        lots=payload.lots,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ─── Personal trade journal (stats only — not reward lots) ─────────
@app.get("/api/me/trade-journal", response_model=list[schemas.TradeJournalOut])
def list_trade_journal(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(TradeJournal)
        .filter(TradeJournal.user_id == user.id)
        .order_by(desc(TradeJournal.traded_at), desc(TradeJournal.id))
        .limit(min(limit, 200))
        .all()
    )


@app.get("/api/me/trade-journal/summary", response_model=schemas.TradeJournalSummaryOut)
def trade_journal_summary(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    uid = user.id
    total_orders = int(db.query(func.count(TradeJournal.id)).filter(
        TradeJournal.user_id == uid
    ).scalar() or 0)
    orders_with_pnl = int(
        db.query(func.count(TradeJournal.id))
        .filter(TradeJournal.user_id == uid, TradeJournal.pnl.isnot(None))
        .scalar()
        or 0
    )
    total_pnl = (
        db.query(func.coalesce(func.sum(TradeJournal.pnl), 0.0))
        .filter(TradeJournal.user_id == uid, TradeJournal.pnl.isnot(None))
        .scalar()
        or 0.0
    )
    wins = int(
        db.query(func.count(TradeJournal.id))
        .filter(TradeJournal.user_id == uid, TradeJournal.pnl > 0)
        .scalar()
        or 0
    )
    losses = int(
        db.query(func.count(TradeJournal.id))
        .filter(TradeJournal.user_id == uid, TradeJournal.pnl < 0)
        .scalar()
        or 0
    )
    be = int(
        db.query(func.count(TradeJournal.id))
        .filter(TradeJournal.user_id == uid, TradeJournal.pnl == 0)
        .scalar()
        or 0
    )
    return schemas.TradeJournalSummaryOut(
        total_orders=total_orders,
        orders_with_pnl=orders_with_pnl,
        total_pnl=round(float(total_pnl), 2),
        wins=wins,
        losses=losses,
        break_even=be,
    )


@app.post(
    "/api/me/trade-journal",
    response_model=schemas.TradeJournalOut,
    status_code=201,
)
def add_trade_journal(
    payload: schemas.TradeJournalIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    when = payload.traded_at
    if when is None:
        when = datetime.now(timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    row = TradeJournal(
        user_id=user.id,
        symbol=payload.symbol.strip().upper(),
        side=payload.side.lower(),
        lot_size=payload.lot_size,
        pnl=payload.pnl,
        note=(payload.note or "").strip() or None,
        traded_at=when,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Claims ────────────────────────────────────────────────────────
@app.get("/api/me/claims", response_model=list[schemas.ClaimOut])
def my_claims(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(RewardClaim)
        .filter(RewardClaim.user_id == user.id)
        .order_by(desc(RewardClaim.claimed_at))
        .all()
    )


@app.post("/api/me/claims", response_model=schemas.ClaimOut, status_code=201)
def claim_reward(
    payload: schemas.ClaimIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tier = next((t for t in TIERS if t["key"] == payload.tier_key.lower()), None)
    if not tier or tier["rank"] == 0:
        raise HTTPException(status_code=400, detail="Tier ไม่ถูกต้อง")

    total = db.query(func.coalesce(func.sum(LotEntry.lots), 0.0)).filter(LotEntry.user_id == user.id).scalar() or 0.0
    if total < tier["lots_required"]:
        raise HTTPException(status_code=400, detail=f"ยังเทรดไม่ถึง {tier['lots_required']} Lots")

    already = db.query(RewardClaim).filter(
        RewardClaim.user_id == user.id, RewardClaim.tier == tier["key"]
    ).first()
    if already:
        raise HTTPException(status_code=409, detail="คุณได้รับรางวัลในระดับนี้แล้ว")

    claim = RewardClaim(user_id=user.id, tier=tier["key"], reward_name=tier["reward"])
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


# ─── Leaderboard ───────────────────────────────────────────────────
@app.get("/api/leaderboard", response_model=list[schemas.LeaderRow])
def leaderboard(limit: int = 10, db: Session = Depends(get_db)):
    rows = (
        db.query(User.display_handle, User.email, func.coalesce(func.sum(LotEntry.lots), 0.0).label("total"))
        .outerjoin(LotEntry, LotEntry.user_id == User.id)
        .group_by(User.id)
        .order_by(desc("total"))
        .limit(min(limit, 50))
        .all()
    )
    out: list[schemas.LeaderRow] = []
    for i, (handle, email, total) in enumerate(rows, start=1):
        if total <= 0:
            continue
        tier = tier_for_lots(total)
        out.append(
            schemas.LeaderRow(
                rank=i,
                handle=handle or _generate_handle(email),
                tier_name=tier["name"],
                tier_key=tier["key"],
                total_lots=round(total, 2),
            )
        )
    return out


# ─── Admin: CSV import ─────────────────────────────────────────────
def _build_preview(report: ParseReport, file_hash: str, filename: str, db: Session) -> schemas.CsvPreviewOut:
    """Compute the dry-run preview from a parsed report."""
    already = (
        db.query(CsvImport)
        .filter(CsvImport.file_hash == file_hash)
        .order_by(desc(CsvImport.created_at))
        .first()
    )

    # Map MT id → User
    mt_ids = list(report.unique_mt_ids)
    users_by_xm: dict[str, User] = {}
    if mt_ids:
        for u in db.query(User).filter(User.xm_id.in_(mt_ids)).all():
            if u.xm_id:
                users_by_xm[u.xm_id] = u

    # Existing external_trade_ids in DB so we can detect duplicates
    existing_ext_ids: set[str] = set()
    if report.trades:
        ext_ids = list({t.external_trade_id for t in report.trades})
        for chunk_start in range(0, len(ext_ids), 500):
            chunk = ext_ids[chunk_start:chunk_start + 500]
            rows = db.query(LotEntry.external_trade_id).filter(
                LotEntry.source == "partner_csv",
                LotEntry.external_trade_id.in_(chunk),
            ).all()
            existing_ext_ids.update(r[0] for r in rows if r[0])

    # Aggregate per-MT id
    by_mt: dict[str, dict] = {}
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    new_lots_total = 0.0
    new_rows = 0
    duplicate_rows = 0

    for t in report.trades:
        if period_start is None or t.traded_at < period_start:
            period_start = t.traded_at
        if period_end is None or t.traded_at > period_end:
            period_end = t.traded_at

        is_dup = t.external_trade_id in existing_ext_ids
        if is_dup:
            duplicate_rows += 1
        else:
            new_rows += 1
            new_lots_total += t.lots

        bucket = by_mt.setdefault(t.mt_id, {
            "mt_id": t.mt_id,
            "trade_count": 0, "new_trade_count": 0,
            "lots_sum": 0.0, "new_lots_sum": 0.0,
        })
        bucket["trade_count"] += 1
        bucket["lots_sum"] += t.lots
        if not is_dup:
            bucket["new_trade_count"] += 1
            bucket["new_lots_sum"] += t.lots

    by_mt_summaries: list[schemas.CsvPreviewMtSummary] = []
    matched_users = 0
    unmatched: list[str] = []
    for mt_id, b in sorted(by_mt.items(), key=lambda x: -x[1]["lots_sum"]):
        u = users_by_xm.get(mt_id)
        if u:
            matched_users += 1
        else:
            unmatched.append(mt_id)
        by_mt_summaries.append(schemas.CsvPreviewMtSummary(
            mt_id=mt_id,
            matched=u is not None,
            user_name=u.name if u else None,
            user_email=u.email if u else None,
            trade_count=b["trade_count"],
            new_trade_count=b["new_trade_count"],
            lots_sum=round(b["lots_sum"], 2),
            new_lots_sum=round(b["new_lots_sum"], 2),
        ))

    return schemas.CsvPreviewOut(
        filename=filename,
        file_hash=file_hash,
        already_imported=already is not None,
        total_rows=len(report.trades) + len(report.errors),
        parsed_rows=len(report.trades),
        error_rows=len(report.errors),
        duplicate_rows=duplicate_rows,
        new_rows=new_rows,
        matched_users=matched_users,
        unmatched_mt_ids=unmatched,
        total_lots_in_file=report.total_lots,
        new_lots_to_add=round(new_lots_total, 2),
        period_start=period_start,
        period_end=period_end,
        by_mt_id=by_mt_summaries,
        sample_errors=report.errors[:10],
    )


@app.post("/api/admin/csv/preview", response_model=schemas.CsvPreviewOut)
async def admin_csv_preview(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="ไฟล์ว่างเปล่า")
    file_hash = hashlib.sha256(raw).hexdigest()

    report = parse_csv_bytes(raw)
    if not report.trades and report.errors:
        raise HTTPException(status_code=400, detail={
            "message": "อ่านไฟล์ไม่สำเร็จ — ตรวจสอบหัวคอลัมน์",
            "errors": report.errors[:10],
        })

    return _build_preview(report, file_hash, file.filename or "uploaded.csv", db)


@app.post("/api/admin/csv/import", response_model=schemas.CsvImportOut, status_code=201)
async def admin_csv_import(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="ไฟล์ว่างเปล่า")
    file_hash = hashlib.sha256(raw).hexdigest()
    # Note: same file can be re-uploaded — the per-trade external_trade_id unique
    # constraint protects against duplicate inserts. Re-uploading is the intended
    # workflow after fixing MT ID assignments.

    report = parse_csv_bytes(raw)
    if not report.trades:
        raise HTTPException(status_code=400, detail={
            "message": "ไม่มีรายการที่จะ import",
            "errors": report.errors[:10],
        })

    # Resolve users
    mt_ids = list(report.unique_mt_ids)
    users_by_xm: dict[str, User] = {}
    if mt_ids:
        for u in db.query(User).filter(User.xm_id.in_(mt_ids)).all():
            if u.xm_id:
                users_by_xm[u.xm_id] = u

    existing_ext_ids: set[str] = set()
    ext_ids = list({t.external_trade_id for t in report.trades})
    for chunk_start in range(0, len(ext_ids), 500):
        chunk = ext_ids[chunk_start:chunk_start + 500]
        rows = db.query(LotEntry.external_trade_id).filter(
            LotEntry.source == "partner_csv",
            LotEntry.external_trade_id.in_(chunk),
        ).all()
        existing_ext_ids.update(r[0] for r in rows if r[0])

    job = CsvImport(
        uploaded_by_id=admin.id,
        filename=file.filename or "uploaded.csv",
        file_hash=file_hash,
        total_rows=len(report.trades) + len(report.errors),
    )
    db.add(job)
    db.flush()  # get job.id

    imported = 0
    skipped_dup = 0
    unmatched_rows = 0
    matched_user_ids: set[int] = set()
    total_lots_added = 0.0

    for t in report.trades:
        if t.external_trade_id in existing_ext_ids:
            skipped_dup += 1
            continue
        u = users_by_xm.get(t.mt_id)
        if not u:
            unmatched_rows += 1
            continue

        db.add(LotEntry(
            user_id=u.id,
            symbol=t.symbol,
            side=t.side,
            lots=t.lots,
            traded_at=t.traded_at,
            source="partner_csv",
            external_trade_id=t.external_trade_id,
            commission=t.commission,
            account_currency=t.account_currency,
            import_id=job.id,
        ))
        existing_ext_ids.add(t.external_trade_id)  # guard against dups inside the same file
        imported += 1
        total_lots_added += t.lots
        matched_user_ids.add(u.id)

    job.imported_rows = imported
    job.skipped_duplicates = skipped_dup
    job.unmatched_rows = unmatched_rows
    job.matched_users = len(matched_user_ids)
    job.total_lots_added = round(total_lots_added, 2)

    db.commit()
    db.refresh(job)
    return job


@app.get("/api/admin/csv/imports", response_model=list[schemas.CsvImportOut])
def admin_list_imports(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(CsvImport)
        .order_by(desc(CsvImport.created_at))
        .limit(50)
        .all()
    )


@app.get("/api/admin/users", response_model=list[schemas.AdminUserRow])
def admin_list_users(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            User.id, User.name, User.email, User.xm_id, User.display_handle, User.is_admin,
            func.coalesce(func.sum(LotEntry.lots), 0.0).label("total"),
        )
        .outerjoin(LotEntry, LotEntry.user_id == User.id)
        .group_by(User.id)
        .order_by(desc("total"))
        .all()
    )
    return [
        schemas.AdminUserRow(
            id=r[0], name=r[1], email=r[2], xm_id=r[3], display_handle=r[4],
            is_admin=bool(r[5]), total_lots=round(float(r[6] or 0), 2),
        )
        for r in rows
    ]


@app.patch("/api/admin/users/{user_id}", response_model=schemas.AdminUserRow)
def admin_update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="ไม่พบสมาชิกนี้")

    if payload.xm_id is not None:
        new_xm = payload.xm_id.strip() or None
        if new_xm and new_xm != target.xm_id:
            clash = db.query(User).filter(
                User.xm_id == new_xm, User.id != target.id
            ).first()
            if clash:
                raise HTTPException(
                    status_code=409,
                    detail=f"MT ID นี้ถูกใช้งานโดย {clash.name} ({clash.email})",
                )
        target.xm_id = new_xm

    if payload.name is not None:
        new_name = payload.name.strip()
        if new_name:
            target.name = new_name

    if payload.display_handle is not None:
        target.display_handle = payload.display_handle.strip() or None

    if payload.is_admin is not None and target.id != admin.id:
        target.is_admin = bool(payload.is_admin)

    db.commit()
    db.refresh(target)

    total = db.query(func.coalesce(func.sum(LotEntry.lots), 0.0)).filter(
        LotEntry.user_id == target.id
    ).scalar() or 0.0

    return schemas.AdminUserRow(
        id=target.id,
        name=target.name,
        email=target.email,
        xm_id=target.xm_id,
        display_handle=target.display_handle,
        total_lots=round(float(total), 2),
        is_admin=bool(target.is_admin),
    )


@app.post(
    "/api/admin/users/placeholder",
    response_model=schemas.CreatePlaceholdersOut,
    status_code=201,
)
def admin_create_placeholders(
    payload: schemas.CreatePlaceholdersIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create stub User rows for MT IDs that aren't yet linked to a member.

    Each placeholder gets a locked password (a random secret hashed) so it can't
    be logged into directly. The real customer can later register through the
    normal flow with the same MT ID — that registration endpoint can be taught
    to merge into the placeholder, but for now placeholders simply hold the lots
    until ownership is claimed.
    """
    import secrets

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in payload.mt_ids:
        v = (raw or "").strip()
        if v and v not in seen:
            seen.add(v)
            cleaned.append(v)

    if not cleaned:
        raise HTTPException(status_code=400, detail="ไม่มี MT ID ให้สร้าง")

    existing = {
        u.xm_id for u in db.query(User).filter(User.xm_id.in_(cleaned)).all()
        if u.xm_id
    }
    skipped = [m for m in cleaned if m in existing]
    to_create = [m for m in cleaned if m not in existing]

    prefix = payload.name_prefix.strip() or "Client"
    locked_pw = hash_password(secrets.token_urlsafe(32))
    created_users: list[User] = []

    for mt_id in to_create:
        suffix = mt_id[-4:] if len(mt_id) >= 4 else mt_id
        user = User(
            name=f"{prefix} {mt_id}",
            email=f"mt_{mt_id}{PLACEHOLDER_EMAIL_DOMAIN}",
            password_hash=locked_pw,
            xm_id=mt_id,
            display_handle=f"{prefix}_{suffix}",
            account_type="Standard",
        )
        db.add(user)
        created_users.append(user)

    db.commit()

    out_rows: list[schemas.AdminUserRow] = []
    for u in created_users:
        db.refresh(u)
        out_rows.append(schemas.AdminUserRow(
            id=u.id, name=u.name, email=u.email, xm_id=u.xm_id,
            display_handle=u.display_handle, total_lots=0.0,
            is_admin=bool(u.is_admin),
        ))

    return schemas.CreatePlaceholdersOut(created=out_rows, skipped=skipped)


# ─── Helpers ───────────────────────────────────────────────────────
def _generate_handle(email: str) -> str:
    """Return a privacy-friendly handle like 'L*****d_FX' from an email."""
    base = email.split("@", 1)[0]
    if len(base) <= 2:
        masked = base + "***"
    else:
        masked = base[0] + ("*" * max(3, len(base) - 2)) + base[-1]
    return masked


def _value_estimate(value_thb: str) -> int:
    """Pick a midpoint THB number from the tier value string."""
    if not value_thb or value_thb == "—":
        return 0
    cleaned = value_thb.replace(",", "").replace("฿", "").replace("+", "").strip()
    try:
        if "–" in cleaned:
            lo, hi = cleaned.split("–", 1)
            return int((int(lo) + int(hi)) / 2)
        return int(cleaned)
    except ValueError:
        return 0


# ─── Static frontend ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def root_index():
    return FileResponse(ROOT / "index.html")


# Serve any *.html / *.css / *.js / *.svg / *.ico file in the project root.
@app.get("/{path:path}", include_in_schema=False)
def static_root(path: str):
    candidate = ROOT / path
    if candidate.is_file() and candidate.suffix in {".html", ".css", ".js", ".svg", ".ico", ".png", ".jpg", ".webp"}:
        return FileResponse(candidate)
    # Fall back to index for unknown routes (SPA-style).
    return FileResponse(ROOT / "index.html")
