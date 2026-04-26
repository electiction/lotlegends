# Deploy guide — Render.com (free tier, with Postgres)

This walks you through getting **The Lot Legends** live on a public URL,
end-to-end. Total time: ~30 minutes.

## What you'll get

- Public HTTPS URL (e.g. `https://lotlegends.onrender.com`)
- Postgres database with daily backups (free tier: 1 GB, 90-day retention)
- Auto-deploy on every git push to `main`
- Singapore region (lowest latency for Thailand)
- Bootstrap admin auto-created on first startup

## Prerequisites

- ✅ GitHub account
- ✅ Git installed locally (you have v2.50)
- A Render.com account (free, sign up at https://render.com — use "Sign up with GitHub" so it links automatically)

---

## Step 1 — Push the code to GitHub

> Run these from the project root: `c:\Users\User\OneDrive\Desktop\rewardxm`

### 1.1 Create an empty repo on GitHub

1. Go to <https://github.com/new>
2. Repository name: `lotlegends` (or anything you prefer)
3. **Private** (recommended — your data + secrets, even though .env is gitignored)
4. **Do NOT** check "Add a README", "Add .gitignore", or license — we have those
5. Click **Create repository**

GitHub will show you a "…or push an existing repository from the command line" snippet. Copy the URL it shows (looks like `https://github.com/<your-username>/lotlegends.git`).

### 1.2 Initialize and push

```powershell
git init
git branch -M main
git add .
git commit -m "Initial commit — The Lot Legends rewards platform"
git remote add origin https://github.com/<your-username>/lotlegends.git
git push -u origin main
```

If git asks you to log in, use a **personal access token** as the password
(GitHub no longer accepts passwords): <https://github.com/settings/tokens/new?scopes=repo>

✅ When `git push` finishes, refresh your repo on GitHub — you should see all the files.

---

## Step 2 — Deploy on Render via Blueprint

Render reads `render.yaml` (already in this repo) and provisions:
1. The **Postgres database** (free tier)
2. The **FastAPI web service**

…with `DATABASE_URL` pre-wired between them.

### 2.1 Connect Render to GitHub

1. Log into <https://dashboard.render.com>
2. If this is your first time: click **"GitHub"** under "Connect account" and grant access to the `lotlegends` repo
3. Click **"New +"** → **"Blueprint"**
4. Pick the `lotlegends` repository
5. Click **Connect**

Render will read `render.yaml` and ask you to fill in two **secrets**:

| Variable | What to put |
|----------|-------------|
| `BOOTSTRAP_ADMIN_EMAIL` | The email you want to log in as admin (e.g. `chris@yourdomain.com`) |
| `BOOTSTRAP_ADMIN_PASSWORD` | A strong password (≥ 12 chars, mix letters/numbers/symbols) |

Everything else (`LOTLEGENDS_SECRET`, `DATABASE_URL`, `LOTLEGENDS_ENV`) is auto-generated.

### 2.2 Click "Apply"

Render will:
- Spin up a Postgres database (~2 min)
- Build your service: `pip install -r backend/requirements.txt` (~3 min)
- Start the service: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Hit `/api/health` to confirm it's alive

When status turns 🟢 **"Live"** the URL appears at the top of the page. Click it.

### 2.3 First login

1. Open `https://your-service.onrender.com/login.html`
2. Sign in with the email & password you set as `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`
3. You should see the **Admin** link in the nav.
4. **Important:** rotate the bootstrap password from inside the app or by changing the env var on Render — anyone who reads your Render env tab can see it otherwise.

---

## Step 3 — Smoke test the customer flow

1. Open an incognito window
2. Visit `https://your-service.onrender.com/`
3. Click **"เข้าร่วม"** → fill in the form
4. **Test the claim feature:** in step 2, type the MT ID `420298067`. After ~350ms, a gold banner should appear: *"พบ Lots ที่สะสมไว้แล้ว!"* (works only if you've imported a CSV that contains that MT ID — see step 4 below)
5. Submit → you should auto-redirect to the dashboard with the claimed Lots already showing

---

## Step 4 — Import your real Partner CSV

Once live, log in as admin, go to **Admin → CSV Import**, drag in `traderTrades.csv`. The flow is identical to local:

1. Upload → review preview
2. (Optional) **"สร้างบัญชี Placeholder ทั้งหมด"** for unmatched MT IDs
3. Confirm → Lots are credited
4. Customers can now register with their MT ID and the Lots auto-merge into their account

---

## Common operations

### Deploy a new version

Just push to `main`. Render auto-deploys.

```powershell
git add .
git commit -m "Your change"
git push
```

Watch the deploy at: **Render Dashboard → lotlegends → Events**

### View logs

**Render Dashboard → lotlegends → Logs**

Live tail of `uvicorn` output. Searchable for errors.

### Connect a custom domain

1. **Render Dashboard → lotlegends → Settings → Custom Domains → Add**
2. Enter your domain (e.g. `rewards.yourbroker.co.th`)
3. Render gives you a DNS CNAME record — add it to your registrar
4. Wait 5–60 minutes for DNS + auto-SSL

### Promote another user to admin

Two options:

**A — From the Render shell:**

```bash
# Render Dashboard → lotlegends → Shell tab
python -c "
from backend.database import SessionLocal
from backend.models import User
db = SessionLocal()
u = db.query(User).filter_by(email='someone@example.com').first()
u.is_admin = True
db.commit()
print('Promoted', u.email)
"
```

**B — Set `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` to the new
person's credentials and redeploy.** The bootstrap routine promotes existing
users with that email to admin.

### Reset the database

⚠️ Destroys all data. Only do this for a fresh start.

1. Render Dashboard → `lotlegends-db` → **Settings** → "Delete database"
2. Re-deploy the web service — it'll create empty tables on next startup
3. Re-trigger the bootstrap admin (or set fresh env vars and redeploy)

---

## Free-tier caveats

- **Sleeping**: free web services spin down after **15 min** of no traffic. The first request after sleep takes ~30 sec to wake up. To keep it warm, either upgrade to "Starter" ($7/mo) or hit `/api/health` from an external uptime monitor like UptimeRobot every 10 min.
- **Postgres expiry**: free Postgres expires after **30 days**. Render emails you 7 days before. Either upgrade ($7/mo) or migrate to a fresh free DB (data export + import).
- **Build time**: free instances build slowly (~3–5 min). Paid is ~30 sec.

---

## Alternative: Railway, Fly.io, your own VPS

The same code runs anywhere that supports Python 3.12 + Postgres. Key things:

| Need | Where it goes |
|------|---------------|
| Build command | `pip install -r backend/requirements.txt` |
| Start command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Env vars | `LOTLEGENDS_ENV=production`, `LOTLEGENDS_SECRET=…`, `DATABASE_URL=…`, `BOOTSTRAP_ADMIN_EMAIL/PASSWORD` |
| Healthcheck | `GET /api/health` returns `200` |

A `Procfile` (already included) is enough for Heroku-style PaaS.

---

## Security checklist before launching to real customers

- [ ] `LOTLEGENDS_ENV=production` is set
- [ ] `LOTLEGENDS_SECRET` is the auto-generated one from Render (never a hand-typed string)
- [ ] Bootstrap admin password rotated to something unique
- [ ] Repo is **private** on GitHub (so you can keep `lotlegends.db` and any test CSVs out of public view — they're gitignored, but defense in depth)
- [ ] Custom domain has SSL (Render gives Let's Encrypt for free)
- [ ] (Optional) Add an external uptime monitor → email you when the site goes down
- [ ] (Optional but recommended) Remove the demo accounts (`*.lotlegends.dev` from `seed.py`) before customers arrive — or just don't run `python -m backend.seed` on production

You're set. Welcome to production.
