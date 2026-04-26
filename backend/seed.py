"""Seed the database with mock users + lot entries so the leaderboard isn't empty."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .auth import hash_password
from .database import SessionLocal, init_db
from .models import LotEntry, User

MOCK_USERS = [
    ("Chris L.",      "chris@lotlegends.dev",   "demo1234", "24091877", "MasterTH_FX",  720),
    ("Phon T.",       "phon@lotlegends.dev",    "demo1234", "24112233", "PhonZilla",    684),
    ("Nat W.",        "nat@lotlegends.dev",     "demo1234", "24112244", "NatScalp",     612),
    ("Anan K.",       "anan@lotlegends.dev",    "demo1234", "24112255", "GoldHunter",   548),
    ("Kanya R.",      "kanya@lotlegends.dev",   "demo1234", "24112266", "KanyaSwing",   421),
    ("Ake P.",        "ake@lotlegends.dev",     "demo1234", "24112277", "AkeFX",        388),
    ("Mook S.",       "mook@lotlegends.dev",    "demo1234", "24112288", "MookScalper",  312),
    ("Tar V.",        "tar@lotlegends.dev",     "demo1234", "24112299", "TarTrend",     245),
    ("Beam D.",       "beam@lotlegends.dev",    "demo1234", "24112300", "BeamSafe",     188),
    ("Ploy N.",       "ploy@lotlegends.dev",    "demo1234", "24112311", "PloyDay",      142),
    ("Demo User",     "demo@lotlegends.dev",    "demo1234", "24999999", "DemoUser",     0),  # zero so beginners can test
]

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "US30", "NAS100"]


def _spread_lots(total: float, days: int = 60) -> list[tuple[float, datetime, str, str]]:
    """Distribute the total across N random days, returning (lots, when, symbol, side)."""
    if total <= 0:
        return []

    out: list[tuple[float, datetime, str, str]] = []
    remaining = total
    now = datetime.now(timezone.utc)
    n_entries = random.randint(15, 40)

    for i in range(n_entries):
        if i == n_entries - 1:
            chunk = round(remaining, 2)
        else:
            chunk = round(min(remaining, random.uniform(2, total / 6)), 2)
        if chunk <= 0:
            break
        remaining = round(remaining - chunk, 2)
        when = now - timedelta(days=random.randint(0, days), hours=random.randint(0, 23))
        out.append((chunk, when, random.choice(SYMBOLS), random.choice(["buy", "sell"])))
        if remaining <= 0:
            break

    return out


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("[seed] Database already has users; skipping seed.")
            return

        for name, email, pw, xm_id, handle, total in MOCK_USERS:
            user = User(
                name=name,
                email=email,
                password_hash=hash_password(pw),
                xm_id=xm_id,
                display_handle=handle,
                account_type="Standard",
                target_reward="iPhone 17 Pro Max" if total >= 500 else "iPad Gen 10",
                is_admin=(email == "chris@lotlegends.dev"),
            )
            db.add(user)
            db.flush()

            for lots, when, symbol, side in _spread_lots(total):
                db.add(
                    LotEntry(
                        user_id=user.id,
                        symbol=symbol,
                        side=side,
                        lots=lots,
                        traded_at=when,
                        source="seed",
                    )
                )

        db.commit()
        print(f"[seed] Inserted {len(MOCK_USERS)} users + lot history.")
        print("[seed] Try logging in with:")
        print("       email:    chris@lotlegends.dev")
        print("       password: demo1234")
    finally:
        db.close()


if __name__ == "__main__":
    run()
