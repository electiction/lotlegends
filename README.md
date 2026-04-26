# The Lot Legends

> **Quiet Luxury for Traders.** A rewards program that turns XM trading lots
> into real, tangible rewards — from lifestyle accessories to gold and beyond.

A full-stack web app: minimalist dark-luxury frontend + FastAPI backend
with JWT auth, SQLite storage, and live leaderboards.

---

## Features

### Frontend (vanilla, no build step)
- **Quiet-luxury aesthetic** — dark theme, champagne gold accent, Cormorant Garamond + Inter typography
- **Landing page** (`index.html`) with hero, 8-tier ladder, featured rewards, how-it-works, live leaderboard, FAQ
- **Personal dashboard** (`dashboard.html`) — real-time progress bar, milestones, recent trades, claimable rewards, your standing
- **Multi-step join form** (`join.html`) — Personal → XM Account → Confirm
- **Login page** (`login.html`) with one-click demo accounts
- **Manual lot entry modal** for demo / admin use
- **Responsive** with mobile drawer menu, loading screen, reveal-on-scroll, animated counters

### Backend (Python + FastAPI)
- **JWT auth** (bcrypt password hashing, 14-day tokens)
- **SQLite for dev / Postgres for prod** via SQLAlchemy 2.0 ORM
- **REST API** — register, login, /me, lots, claims, leaderboard, tiers
- **Auto-generated API docs** at `/docs` (Swagger) and `/redoc`
- **Static file serving** — backend serves the frontend too (single port)
- **Tier engine** — single source of truth for the 8-tier ladder
- **Placeholder-claim flow** — when a customer registers with an MT ID that already has Partner-imported Lots, the placeholder account is silently merged into their new account so their Lots show up immediately

### Admin console (`admin.html`)
- **CSV import** for the XM Partner `traderTrades.csv` export
- **Thai column-header parser** (`เทรด #`, `MT4/MT5 ID`, `ประเภทของเทรด: ซื้อ/ขาย`, etc.)
- **Dry-run preview** — see new vs duplicate rows, matched/unmatched MT IDs, and lots-to-add **before** committing
- **Dedup by file hash + per-trade `external_trade_id`** — re-uploading the same file is a no-op
- **Audit log** — every import recorded in `csv_imports` with row counts and totals
- **Member directory** — list every account with current lots and admin flag
- Multiple text encodings supported (UTF-8 / UTF-8-BOM / Windows-874 / TIS-620)

---

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r backend/requirements.txt
```

### 2. Seed the database with demo data
```bash
python -m backend.seed
```

This creates 11 demo users, including the leaderboard top 10 plus a fresh
zero-lot demo account. All demo passwords are `demo1234`.

### 3. Run the server
```bash
python -m uvicorn backend.main:app --reload --port 8765
```

Visit:
- **Site**: http://127.0.0.1:8765/
- **API docs**: http://127.0.0.1:8765/docs

### 4. Log in with a demo account
On the login page, click any demo chip (Chris L., Kanya R., or Demo User)
to auto-fill the credentials, then **เข้าสู่ระบบ**.

---

## Demo accounts (created by `seed.py`)

| Email                       | Lots | Tier    | Password   |
|-----------------------------|-----:|---------|------------|
| `chris@lotlegends.dev`      |  720 | Master  | `demo1234` |
| `phon@lotlegends.dev`       |  684 | Diamond | `demo1234` |
| `nat@lotlegends.dev`        |  612 | Diamond | `demo1234` |
| `anan@lotlegends.dev`       |  548 | Diamond | `demo1234` |
| `kanya@lotlegends.dev`      |  421 | Gold    | `demo1234` |
| `ake@lotlegends.dev`        |  388 | Platinum| `demo1234` |
| `mook@lotlegends.dev`       |  312 | Platinum| `demo1234` |
| `tar@lotlegends.dev`        |  245 | Silver  | `demo1234` |
| `beam@lotlegends.dev`       |  188 | Silver  | `demo1234` |
| `ploy@lotlegends.dev`       |  142 | Silver  | `demo1234` |
| `demo@lotlegends.dev`       |    0 | Novice  | `demo1234` |

To wipe and re-seed, delete `lotlegends.db` and re-run `python -m backend.seed`.

---

## Project Structure

```
rewardxm/
├── index.html             # Landing page
├── dashboard.html         # Personal dashboard
├── join.html              # Sign-up (multi-step)
├── login.html             # Sign-in
├── admin.html             # Admin: CSV import + member directory
├── styles.css             # Quiet-luxury theme
├── script.js              # Shared interactions
├── api.js                 # Frontend API client (JWT in localStorage)
├── assets/                # Hero / tier images
└── backend/
    ├── main.py            # FastAPI app + endpoints
    ├── database.py        # SQLAlchemy engine/session
    ├── models.py          # User, LotEntry, RewardClaim, CsvImport
    ├── schemas.py         # Pydantic request/response models
    ├── auth.py            # bcrypt + JWT helpers
    ├── csv_parser.py      # XM Partner traderTrades.csv parser
    ├── seed.py            # Mock data seeder
    ├── tests/
    │   └── sample_traderTrades.csv  # Example file for testing the parser
    ├── requirements.txt
    └── .env.example
```

---

## Tier ladder

| # | Tier     | Lots Required | Reward                                |
|---|----------|--------------:|---------------------------------------|
| 1 | Starter  |            10 | Apparel set                           |
| 2 | Bronze   |            30 | Backpack / Power Bank                 |
| 3 | Silver   |            70 | Bluetooth headphones                  |
| 4 | Gold     |           150 | Apple Watch SE / Galaxy Watch         |
| 5 | Platinum |           300 | iPad (Gen 10) / AirPods Pro 2         |
| 6 | Diamond  |           500 | MacBook Air M3 / iPhone 16            |
| 7 | Master   |           700 | iPhone 17 Pro Max                     |
| 8 | Legend   |         1,000 | 1 Baht Gold / Overseas Trip           |

---

## API Endpoints

| Method | Path                  | Auth | Description                          |
|--------|-----------------------|:----:|--------------------------------------|
| GET    | `/api/health`         |  —   | Health check                         |
| GET    | `/api/tiers`          |  —   | List all tiers                       |
| GET    | `/api/leaderboard`    |  —   | Top traders                          |
| POST   | `/api/auth/register`  |  —   | Create account → returns JWT (auto-claims placeholder if MT ID matches) |
| GET    | `/api/auth/preview-claim/{mt_id}` |  —   | Tell the join page if Lots are waiting |
| POST   | `/api/auth/login`     |  —   | Login → returns JWT                  |
| GET    | `/api/me`             | JWT  | Current user                         |
| GET    | `/api/me/progress`    | JWT  | Total lots + tier + progress         |
| GET    | `/api/me/lots`        | JWT  | Lot history                          |
| POST   | `/api/me/lots`        | JWT  | Add a lot entry (demo/admin)         |
| GET    | `/api/me/claims`      | JWT  | Claimed rewards                      |
| POST   | `/api/me/claims`      | JWT  | Claim a reward at a reached tier     |
| POST   | `/api/admin/csv/preview`  | Admin | Dry-run a Partner CSV (no writes) |
| POST   | `/api/admin/csv/import`   | Admin | Import a Partner CSV              |
| GET    | `/api/admin/csv/imports`  | Admin | History of imports (audit log)    |
| GET    | `/api/admin/users`        | Admin | List every member with totals     |

Full interactive docs: **http://127.0.0.1:8765/docs**

### Admin workflow

1. Log in as an admin user. The seed script promotes `chris@lotlegends.dev`.
2. Click the **Admin** link in the nav (only visible to admins).
3. Drag-drop the `traderTrades.csv` exported from your XM Partner Portal.
4. Review the preview — matched users, unmatched MT IDs, new vs duplicate rows, and total Lots that would be added.
5. Click **ยืนยันนำเข้า** to commit. Re-uploading the same file is rejected by file hash.

The parser tolerates Thai column headers, `ซื้อ/ขาย` side values, multiple text
encodings, and `DD/MM/YYYY HH:MM:SS` timestamps. Trade rows are deduplicated by
their `เทรด #` (external trade ID).

---

## Configuration

Create `backend/.env` (see `.env.example`):

```
LOTLEGENDS_SECRET=replace-this-with-a-long-random-string
# DATABASE_URL=sqlite:///lotlegends.db
```

For production, switch to Postgres:

```
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/lotlegends
```

---

## Deploy

See **[DEPLOY.md](./DEPLOY.md)** for a step-by-step Render.com walkthrough
(free tier with Postgres, Singapore region, ~30 minutes end-to-end).

The repo includes everything Render needs:
- `render.yaml` — Blueprint spec (one-click "New Blueprint")
- `Procfile` — for Heroku-style PaaS
- `runtime.txt` — pins Python 3.12

## Roadmap

- [x] **Admin CSV import** — Partner-portal `traderTrades.csv` (Thai headers + dedup)
- [x] **Admin member directory** — inline edit MT IDs, bulk placeholder creation
- [x] **Customer claim flow** — register with MT ID → placeholder auto-merges
- [x] **Production deployment** — Render Blueprint with Postgres + bootstrap admin
- [ ] **Schedule auto-imports** (drop the CSV in a watched folder / Dropbox)
- [ ] **XM Partner API integration** — direct daily sync (requires IB approval)
- [ ] **Approve / ship claims** UI for admins
- [ ] **Email + LINE notifications** — tier-up alerts, reward updates
- [ ] **Light mode toggle**

---

## License

Internal project. Not for redistribution.

---

*The Lot Legends · Est. 2026 · Quiet Luxury for Traders*
