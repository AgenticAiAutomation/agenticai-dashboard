# AgenticAI SEO Dashboard

Team-facing web dashboard for AgenticAiAutomation SEO operations. Multi-user system for managing keywords, articles, tasks, and analytics.

## Tech Stack

- **Backend:** FastAPI (Python 3.12), JWT auth, PostgreSQL 16
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Deploy:** Ubuntu 24.04 VPS, nginx, systemd, Cloudflare Pages

## Project Structure

```
agenticai-dashboard/
├── api/                    # FastAPI backend
│   ├── app/
│   │   ├── routes/        # API endpoints (auth, users, keywords, articles, tasks, metrics)
│   │   ├── models.py      # SQLAlchemy models
│   │   ├── schemas.py     # Pydantic schemas
│   │   ├── auth.py        # JWT + bcrypt utilities
│   │   ├── seed.py        # Seed data parser
│   │   └── main.py        # FastAPI app
│   ├── alembic/           # Database migrations
│   ├── requirements.txt
│   └── .env.example
├── web/                   # Next.js frontend
│   ├── app/              # App Router pages
│   ├── components/       # Reusable components
│   ├── lib/api.ts       # Axios client
│   └── package.json
└── infra/               # Deployment configs
    ├── dashboard-api.service
    └── nginx-dashboard.conf
```

## Local Development

### Backend Setup

```bash
cd api
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your database credentials and generate JWT_SECRET_KEY:
# openssl rand -hex 32

# Run migrations
alembic upgrade head

# Seed database (parses SEO_CONTENT_TASKS.md and keyword-cluster.md)
python -m app.seed

# Start API
uvicorn app.main:app --reload --port 5003
```

API runs at `http://localhost:5003`

### Frontend Setup

```bash
cd web
npm install

# Create .env.local
cp .env.local.example .env.local

# Start dev server
npm run dev
```

Frontend runs at `http://localhost:3000`

## Production Deployment

### 1. Database Setup

```bash
# On VPS
sudo -u postgres psql

CREATE DATABASE agenticai_dashboard;
CREATE USER dashboard_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE agenticai_dashboard TO dashboard_user;
\q
```

### 2. Backend Deployment

```bash
# Clone repo to VPS
cd /var/www
sudo git clone <repo-url> agenticai-dashboard
cd agenticai-dashboard/api

# Copy seed data files
sudo mkdir -p /var/www/agenticai-dashboard/seed-data
sudo cp /path/to/SEO_CONTENT_TASKS.md /var/www/agenticai-dashboard/seed-data/
sudo cp /path/to/keyword-cluster.md /var/www/agenticai-dashboard/seed-data/

# Python environment
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt

# Configure .env
sudo nano .env
# Set DATABASE_URL, JWT_SECRET_KEY, INITIAL_OWNER_PASSWORD, CORS_ORIGINS

# Run migrations
sudo venv/bin/alembic upgrade head

# Seed database
sudo venv/bin/python -m app.seed

# Setup systemd service
sudo cp /var/www/agenticai-dashboard/infra/dashboard-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard-api
sudo systemctl start dashboard-api
sudo systemctl status dashboard-api
```

### 3. Nginx Setup

```bash
sudo cp /var/www/agenticai-dashboard/infra/nginx-dashboard.conf /etc/nginx/sites-available/dashboard
sudo ln -s /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. SSL Certificate

```bash
sudo certbot --nginx -d api.dashboard.agenticaiautomation.co
```

### 5. Frontend Deployment

- Push `web/` to GitHub
- Connect to Cloudflare Pages:
  - Framework: Next.js
  - Build command: `npm run build`
  - Build output: `.next`
  - Root directory: `web/`
  - Environment variable: `NEXT_PUBLIC_API_URL=https://api.dashboard.agenticaiautomation.co`
- Point `dashboard.agenticaiautomation.co` to Cloudflare Pages

### 6. DNS Configuration

In Cloudflare DNS:

```
A     api.dashboard.agenticaiautomation.co  →  <VPS IP>  (proxied)
CNAME dashboard.agenticaiautomation.co      →  <pages URL>
```

## Environment Variables

### Backend (.env)

```bash
DATABASE_URL=postgresql://dashboard_user:PASSWORD@localhost/agenticai_dashboard
JWT_SECRET_KEY=<32-byte hex from openssl rand -hex 32>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
INITIAL_OWNER_EMAIL=Contact@agenticAiAutomation.co
INITIAL_OWNER_PASSWORD=<change on first login>
CORS_ORIGINS=https://dashboard.agenticaiautomation.co,http://localhost:3000
```

### Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=https://api.dashboard.agenticaiautomation.co
```

## Initial Login

After seeding:

- **Email:** Contact@agenticAiAutomation.co
- **Password:** (from INITIAL_OWNER_PASSWORD in .env)
- **⚠️ Change password immediately after first login!**

## User Roles

| Role | Permissions |
|------|------------|
| **owner** | Full access, user management, phase approvals |
| **seo** | Keyword pipeline, publish schedule, metrics |
| **writer** | Assigned articles only, draft/edit status |
| **viewer** | Read-only |

## API Endpoints

```
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout

GET    /users              (owner only)
POST   /users              (owner only)
DELETE /users/{id}         (owner only)

GET    /keywords           (filter: pillar, status, assignee)
PATCH  /keywords/{id}
POST   /keywords/import    (CSV, seo+owner)

GET    /articles           (kanban view; filter: status, track, assignee)
POST   /articles
PATCH  /articles/{id}

GET    /tasks              (filter: phase, assignee, mine)
PATCH  /tasks/{id}

GET    /metrics/summary    (dashboard widgets)
POST   /metrics            (manual entry v1)
```

## Screens

1. **`/login`** — Email + password authentication
2. **`/dashboard`** — Home: today's tasks, publish schedule, phase progress
3. **`/keywords`** — Table view with filters (pillar, status)
4. **`/articles`** — Kanban board (briefed → drafting → editing → schema → ready → published)
5. **`/countries`** — Grid of 10 country landing pages
6. **`/tasks`** — List with phase filters and checkboxes
7. **`/settings/users`** — User management (owner only)

## Maintenance

```bash
# View API logs
sudo journalctl -u dashboard-api -f

# Restart API
sudo systemctl restart dashboard-api

# Update code
cd /var/www/agenticai-dashboard
sudo git pull origin main
sudo systemctl restart dashboard-api

# Database backup
pg_dump -U dashboard_user agenticai_dashboard > backup-$(date +%Y%m%d).sql

# View nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Seed Data

The seed script (`app/seed.py`) imports:

1. **Tasks** from `SEO_CONTENT_TASKS.md` (phases 0-6)
2. **Keywords** from `keyword-cluster.md` (4 pillars, 32 cluster keywords)
3. **Articles** placeholders:
   - 4 pillar pages
   - 32 cluster articles
   - 10 country landing pages (7 BFSI + 3 Logistics)
4. **Initial owner user**

To re-seed (⚠️ clears existing data):

```bash
# Backup first!
pg_dump agenticai_dashboard > backup.sql

# Re-run seed
cd /var/www/agenticai-dashboard/api
sudo venv/bin/python -m app.seed
```

## Troubleshooting

### API won't start

```bash
sudo systemctl status dashboard-api
sudo journalctl -u dashboard-api -n 50
```

Common issues:
- Database not running: `sudo systemctl status postgresql`
- Wrong Python path in systemd service
- Missing .env file

### Frontend can't reach API

- Check CORS_ORIGINS in API `.env`
- Verify `NEXT_PUBLIC_API_URL` in frontend `.env.local`
- Test API directly: `curl https://api.dashboard.agenticaiautomation.co/health`

### Database connection failed

- Verify DATABASE_URL in `.env`
- Check Postgres is running: `sudo systemctl status postgresql`
- Test connection: `psql -U dashboard_user -d agenticai_dashboard`

## v2 Features (Not in v1)

- GSC API integration
- Bing Webmaster API
- In-app notifications
- Comments on articles
- Content brief PDF export
- Client-facing view

---

Built per `dashboard-spec.md` for AgenticAiAutomation SEO team.
