# Deployment Checklist - AgenticAI Dashboard

Complete this checklist step-by-step for successful deployment.

---

## Pre-Deployment (Local)

- [x] Project built and committed to git
- [x] Seed data files included (`api/seed-data/*.md`)
- [ ] Push to GitHub repository
- [ ] Note your GitHub repo URL: `___________________________`

---

## VPS Access

- [ ] VPS IP address: `___________________________`
- [ ] SSH access confirmed: `ssh user@vps-ip`
- [ ] PostgreSQL 16 running: `sudo systemctl status postgresql`
- [ ] Nginx installed: `nginx -v`
- [ ] Python 3.12 available: `python3 --version`

---

## Step 1: Transfer Code

Choose one method:

### Method A: Git Clone (Recommended)
```bash
# 1. Push to GitHub from local
cd C:\Users\hp\Documents\agenticai-dashboard
git remote add origin https://github.com/YOUR_USERNAME/agenticai-dashboard.git
git push -u origin main

# 2. Clone on VPS
ssh user@vps-ip
cd /var/www
sudo git clone https://github.com/YOUR_USERNAME/agenticai-dashboard.git
```

- [ ] Code cloned to `/var/www/agenticai-dashboard`
- [ ] Files verified: `ls /var/www/agenticai-dashboard`

### Method B: SCP/Rsync
- [ ] Files transferred via scp/rsync
- [ ] Permissions fixed: `sudo chown -R www-data:www-data /var/www/agenticai-dashboard`

---

## Step 2: Database Setup

```bash
# Create database
sudo -u postgres psql
CREATE DATABASE agenticai_dashboard;
CREATE USER dashboard_user WITH PASSWORD 'YourSecurePassword123';
GRANT ALL PRIVILEGES ON DATABASE agenticai_dashboard TO dashboard_user;
\q

# Test connection
psql -U dashboard_user -d agenticai_dashboard -h localhost
```

- [ ] Database `agenticai_dashboard` created
- [ ] User `dashboard_user` created
- [ ] Connection test successful
- [ ] Database password noted: `___________________________`

---

## Step 3: Backend Configuration

```bash
cd /var/www/agenticai-dashboard/api

# Update .env
cp .env.example .env
nano .env
```

Update these values:
- [ ] `DATABASE_URL` with real password
- [ ] `JWT_SECRET_KEY` generated: `openssl rand -hex 32`
- [ ] `INITIAL_OWNER_PASSWORD` changed to secure value
- [ ] `CORS_ORIGINS` includes production domain

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

- [ ] Virtual environment created
- [ ] Dependencies installed

---

## Step 4: Database Migration & Seed

```bash
cd /var/www/agenticai-dashboard/api
source venv/bin/activate

# Run migrations
alembic upgrade head

# Seed database
python -m app.seed
```

Expected output:
- [ ] ✓ Created owner user: Contact@agenticAiAutomation.co
- [ ] ✓ Imported X tasks from SEO_CONTENT_TASKS.md
- [ ] ✓ Imported X keywords from keyword-cluster.md
- [ ] ✓ Created 46 article placeholders

---

## Step 5: Systemd Service

```bash
# Copy service file
sudo cp /var/www/agenticai-dashboard/infra/dashboard-api.service /etc/systemd/system/

# Start service
sudo systemctl daemon-reload
sudo systemctl enable dashboard-api
sudo systemctl start dashboard-api
sudo systemctl status dashboard-api
```

- [ ] Service file installed
- [ ] Service enabled
- [ ] Service active (running)
- [ ] Logs show no errors: `sudo journalctl -u dashboard-api -n 50`

---

## Step 6: Nginx Configuration

```bash
# Copy and enable config
sudo cp /var/www/agenticai-dashboard/infra/nginx-dashboard.conf /etc/nginx/sites-available/dashboard
sudo ln -s /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

- [ ] Nginx config copied
- [ ] Symlink created
- [ ] Config test passed
- [ ] Nginx reloaded

---

## Step 7: DNS Configuration

In Cloudflare DNS:

**A Record:**
- Type: A
- Name: `api.dashboard`
- Content: `<VPS IP>`
- Proxy: Enabled (orange cloud)

- [ ] DNS A record created
- [ ] DNS propagated (test: `nslookup api.dashboard.agenticaiautomation.co`)

---

## Step 8: SSL Certificate

```bash
# Install certbot (if needed)
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d api.dashboard.agenticaiautomation.co

# Test auto-renewal
sudo certbot renew --dry-run
```

- [ ] SSL certificate issued
- [ ] Nginx auto-updated with SSL config
- [ ] Auto-renewal configured
- [ ] HTTPS working: `curl https://api.dashboard.agenticaiautomation.co/health`

---

## Step 9: Frontend Deployment

### Push to GitHub (if not done)
```bash
cd C:\Users\hp\Documents\agenticai-dashboard
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Cloudflare Pages Setup

1. Go to Cloudflare Pages dashboard
2. Create new project
3. Connect GitHub repository: `YOUR_USERNAME/agenticai-dashboard`
4. Configure build:
   - **Framework:** Next.js
   - **Build command:** `cd web && npm install && npm run build`
   - **Build output:** `web/.next`
   - **Root directory:** Leave blank or `web/`
5. Environment variables:
   - `NEXT_PUBLIC_API_URL` = `https://api.dashboard.agenticaiautomation.co`
6. Deploy

- [ ] GitHub repo connected
- [ ] Build settings configured
- [ ] Environment variable set
- [ ] First deployment successful
- [ ] Cloudflare Pages URL noted: `___________________________`

### Custom Domain

1. In Cloudflare Pages → Custom domains
2. Add `dashboard.agenticaiautomation.co`
3. Wait for DNS propagation

- [ ] Custom domain added
- [ ] DNS configured automatically
- [ ] Site accessible: `https://dashboard.agenticaiautomation.co`

---

## Step 10: Verification

### Backend Tests

```bash
# Health check
curl https://api.dashboard.agenticaiautomation.co/health
# Expected: {"status":"healthy"}

# Login test
curl -X POST https://api.dashboard.agenticaiautomation.co/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"Contact@agenticAiAutomation.co","password":"YOUR_PASSWORD"}'
# Expected: {"access_token":"...","refresh_token":"..."}
```

- [ ] Health endpoint responds
- [ ] Login successful
- [ ] Access token received

### Frontend Tests

Visit: `https://dashboard.agenticaiautomation.co`

- [ ] Login page loads
- [ ] Can login with owner credentials
- [ ] Dashboard shows keyword count
- [ ] Dashboard shows article count
- [ ] Keywords page shows imported data
- [ ] Articles kanban board displays
- [ ] Tasks page shows imported tasks
- [ ] Countries page shows 10 pages
- [ ] Settings/Users page accessible (owner only)

---

## Step 11: Post-Deployment

### Change Initial Password

- [ ] Login as owner
- [ ] Change password (via Settings or database)
- [ ] Test login with new password

### Create Team Members

- [ ] Add SEO team member
- [ ] Add Writer (if needed)
- [ ] Test role permissions

### Database Backup

```bash
# Create backup
pg_dump -U dashboard_user agenticai_dashboard > ~/dashboard-backup-$(date +%Y%m%d).sql

# Setup automated backups (optional)
# Add to crontab: 0 2 * * * pg_dump -U dashboard_user agenticai_dashboard > ~/backups/dashboard-$(date +\%Y\%m\%d).sql
```

- [ ] Manual backup created
- [ ] Backup location noted: `___________________________`

---

## Monitoring

### Service Health

```bash
# API status
sudo systemctl status dashboard-api

# View logs
sudo journalctl -u dashboard-api -f

# Check port
sudo lsof -i :5003
```

### Set up monitoring (optional)

- [ ] UptimeRobot or similar for uptime monitoring
- [ ] Alert email configured
- [ ] Cloudflare analytics enabled

---

## Rollback Plan

If something goes wrong:

1. **API issues:**
   ```bash
   sudo systemctl stop dashboard-api
   # Fix issue, then:
   sudo systemctl start dashboard-api
   ```

2. **Database issues:**
   ```bash
   psql -U dashboard_user agenticai_dashboard < backup-file.sql
   ```

3. **Frontend issues:**
   - Redeploy via Cloudflare Pages dashboard
   - Or push fix to GitHub (auto-deploys)

---

## Success Criteria

All must be ✓ before declaring success:

- [ ] Backend API responding at `https://api.dashboard.agenticaiautomation.co`
- [ ] Frontend accessible at `https://dashboard.agenticaiautomation.co`
- [ ] Can login with owner account
- [ ] All 7 screens functional
- [ ] Seeded data visible (keywords, articles, tasks)
- [ ] SSL certificates valid
- [ ] Systemd service auto-starts on reboot
- [ ] Team can create accounts and login
- [ ] Initial owner password changed
- [ ] Database backup created

---

## Emergency Contacts

- **VPS Host:** Hostinger Support
- **DNS/CDN:** Cloudflare Support
- **Database:** Postgres docs / DBA
- **Developer:** Jai (jai.prajapati91@gmail.com)

---

## Deployment Date

**Deployed by:** ___________________________  
**Date:** ___________________________  
**Time:** ___________________________  
**Notes:** ___________________________

---

**Status:** [ ] Planning [ ] In Progress [ ] Complete [ ] Failed

**Sign-off:** ___________________________
