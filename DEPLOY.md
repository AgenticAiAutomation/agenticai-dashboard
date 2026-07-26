# Deployment Guide - AgenticAI Dashboard

## Prerequisites on VPS

You'll need access to the VPS where agenticai and leadwa are already running.

- Ubuntu 24.04
- Postgres 16 (already installed)
- Python 3.12
- Node.js 18+ (for local frontend build)
- nginx (already configured)

---

## Step 1: Transfer Files to VPS

From your local machine, transfer the project:

```bash
# Option A: Using rsync (recommended)
rsync -avz --exclude 'node_modules' --exclude 'venv' --exclude '.next' \
  C:\Users\hp\Documents\agenticai-dashboard/ \
  your-user@your-vps-ip:/var/www/agenticai-dashboard/

# Option B: Using scp
scp -r C:\Users\hp\Documents\agenticai-dashboard \
  your-user@your-vps-ip:/var/www/

# Option C: Via git (push to GitHub first, then clone on VPS)
cd C:\Users\hp\Documents\agenticai-dashboard
git init
git add .
git commit -m "Initial dashboard build"
git remote add origin <your-repo-url>
git push -u origin main

# Then on VPS:
cd /var/www
sudo git clone <your-repo-url> agenticai-dashboard
```

---

## Step 2: Database Setup (on VPS)

```bash
# SSH into VPS
ssh your-user@your-vps-ip

# Create database and user
sudo -u postgres psql <<EOF
CREATE DATABASE agenticai_dashboard;
CREATE USER dashboard_user WITH PASSWORD 'YourSecurePassword123';
GRANT ALL PRIVILEGES ON DATABASE agenticai_dashboard TO dashboard_user;
\q
EOF

# Test connection
psql -U dashboard_user -d agenticai_dashboard -h localhost
# Enter password when prompted, then \q to exit
```

---

## Step 3: Backend Setup (on VPS)

```bash
cd /var/www/agenticai-dashboard/api

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
nano .env
# Update these values:
# - DATABASE_URL with your actual password
# - JWT_SECRET_KEY (generate with: openssl rand -hex 32)
# - INITIAL_OWNER_PASSWORD (change to secure password)

# Run migrations
venv/bin/alembic upgrade head

# Seed database
venv/bin/python -m app.seed

# You should see:
# ✓ Created owner user: Contact@agenticAiAutomation.co
# ✓ Imported X tasks from SEO_CONTENT_TASKS.md
# ✓ Imported X keywords from keyword-cluster.md
# ✓ Created 46 article placeholders

# Test API manually
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5003
# Visit http://your-vps-ip:5003/health (should see {"status":"healthy"})
# Ctrl+C to stop
```

---

## Step 4: Systemd Service (on VPS)

```bash
# Copy service file
sudo cp /var/www/agenticai-dashboard/infra/dashboard-api.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Start service
sudo systemctl enable dashboard-api
sudo systemctl start dashboard-api

# Check status
sudo systemctl status dashboard-api

# View logs
sudo journalctl -u dashboard-api -f
```

---

## Step 5: Nginx Configuration (on VPS)

```bash
# Copy nginx config
sudo cp /var/www/agenticai-dashboard/infra/nginx-dashboard.conf /etc/nginx/sites-available/dashboard

# Create symlink
sudo ln -s /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/

# Test nginx config
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

---

## Step 6: SSL Certificate (on VPS)

```bash
# Install certbot if not already installed
sudo apt install certbot python3-certbot-nginx

# Get certificate for API subdomain
sudo certbot --nginx -d api.dashboard.agenticaiautomation.co

# Certbot will:
# 1. Verify domain ownership
# 2. Issue certificate
# 3. Update nginx config automatically
# 4. Set up auto-renewal

# Test renewal
sudo certbot renew --dry-run
```

---

## Step 7: DNS Configuration

In Cloudflare DNS (dashboard.agenticaiautomation.co zone):

1. **A Record for API:**
   - Type: `A`
   - Name: `api.dashboard`
   - Content: `<your VPS IP>`
   - Proxy status: Proxied (orange cloud)
   - TTL: Auto

2. **Wait for DNS propagation** (1-5 minutes)

3. **Test API endpoint:**
   ```bash
   curl https://api.dashboard.agenticaiautomation.co/health
   # Should return: {"status":"healthy"}
   ```

---

## Step 8: Frontend Deployment (Cloudflare Pages)

### Option A: Deploy via Cloudflare Pages Dashboard

1. **Push code to GitHub:**
   ```bash
   # On local machine
   cd C:\Users\hp\Documents\agenticai-dashboard
   git add web/
   git commit -m "Add frontend"
   git push origin main
   ```

2. **In Cloudflare Pages:**
   - Go to Pages → Create a project
   - Connect to your GitHub repository
   - Configure build:
     - Framework preset: **Next.js**
     - Build command: `cd web && npm install && npm run build`
     - Build output directory: `web/.next`
     - Root directory: `web/`
   - Environment variables:
     - `NEXT_PUBLIC_API_URL` = `https://api.dashboard.agenticaiautomation.co`

3. **Custom domain:**
   - In Pages settings → Custom domains
   - Add: `dashboard.agenticaiautomation.co`
   - Cloudflare will auto-configure DNS

### Option B: Manual Build & Deploy

```bash
# On local machine
cd C:\Users\hp\Documents\agenticai-dashboard\web

# Create production .env
echo "NEXT_PUBLIC_API_URL=https://api.dashboard.agenticaiautomation.co" > .env.production

# Build
npm install
npm run build

# Deploy to Pages via Wrangler CLI
npx wrangler pages deploy .next --project-name=agenticai-dashboard
```

---

## Step 9: Verify Deployment

### Test Backend

```bash
# Health check
curl https://api.dashboard.agenticaiautomation.co/health

# Login test
curl -X POST https://api.dashboard.agenticaiautomation.co/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"Contact@agenticAiAutomation.co","password":"ChangeMe123!"}'

# Should return: {"access_token":"...","refresh_token":"...","token_type":"bearer"}
```

### Test Frontend

1. Visit: `https://dashboard.agenticaiautomation.co`
2. Login with:
   - Email: `Contact@agenticAiAutomation.co`
   - Password: (from your `.env` INITIAL_OWNER_PASSWORD)
3. You should see dashboard with:
   - Keyword count
   - Article count
   - Phase progress bars

---

## Step 10: Post-Deployment

### Change Initial Password

1. Login to dashboard
2. Go to Settings → Users
3. Create new owner account with secure password
4. Login with new account
5. Delete initial owner or change password via database:

```bash
# On VPS
cd /var/www/agenticai-dashboard/api
source venv/bin/activate
python3 <<EOF
from app.database import SessionLocal
from app.models import User
from app.auth import get_password_hash

db = SessionLocal()
user = db.query(User).filter(User.email == "Contact@agenticAiAutomation.co").first()
user.password_hash = get_password_hash("NewSecurePassword123!")
db.commit()
print("Password updated")
EOF
```

### Add Team Members

Login as owner → Settings → Users → Add User

---

## Maintenance Commands

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

# Restore backup
psql -U dashboard_user agenticai_dashboard < backup-20260726.sql
```

---

## Troubleshooting

### API won't start

```bash
# Check status
sudo systemctl status dashboard-api

# View detailed logs
sudo journalctl -u dashboard-api -n 100

# Common fixes:
# 1. Database not accessible
sudo systemctl status postgresql

# 2. Wrong permissions
sudo chown -R www-data:www-data /var/www/agenticai-dashboard

# 3. Port already in use
sudo lsof -i :5003
```

### Frontend can't reach API

```bash
# Test API directly
curl https://api.dashboard.agenticaiautomation.co/health

# Check CORS settings in api/.env
grep CORS_ORIGINS /var/www/agenticai-dashboard/api/.env

# Should include: https://dashboard.agenticaiautomation.co
```

### Database connection failed

```bash
# Test connection
psql -U dashboard_user -d agenticai_dashboard

# Check DATABASE_URL in .env
grep DATABASE_URL /var/www/agenticai-dashboard/api/.env

# Verify user exists
sudo -u postgres psql -c "\du"
```

---

## Success Checklist

- [ ] Database created and accessible
- [ ] Backend running on port 5003
- [ ] Systemd service enabled and active
- [ ] Nginx proxying api.dashboard.agenticaiautomation.co
- [ ] SSL certificate issued and auto-renewing
- [ ] Frontend deployed to Cloudflare Pages
- [ ] Custom domain dashboard.agenticaiautomation.co working
- [ ] Can login and see seeded data
- [ ] All 7 screens functional
- [ ] Initial password changed

---

**You're done! Dashboard is live at:**
- Frontend: `https://dashboard.agenticaiautomation.co`
- API: `https://api.dashboard.agenticaiautomation.co`
