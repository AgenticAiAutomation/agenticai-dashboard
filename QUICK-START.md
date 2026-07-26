# Quick Start Guide

Get the dashboard running in 15 minutes.

---

## Prerequisites

- VPS with Ubuntu 24.04
- PostgreSQL 16
- Domain: `dashboard.agenticaiautomation.co`
- Cloudflare account

---

## 3-Step Deploy

### 1. On Local Machine

```bash
# Push to GitHub
cd C:\Users\hp\Documents\agenticai-dashboard
git remote add origin https://github.com/YOUR_USERNAME/agenticai-dashboard.git
git push -u origin main
```

### 2. On VPS (Automated)

```bash
# Clone and run setup script
cd /var/www
sudo git clone https://github.com/YOUR_USERNAME/agenticai-dashboard.git
cd agenticai-dashboard

# Make setup script executable
chmod +x scripts/setup-vps.sh

# BEFORE running: Edit api/.env with secure passwords
cp api/.env.example api/.env
nano api/.env
# Update: DATABASE_URL password, JWT_SECRET_KEY, INITIAL_OWNER_PASSWORD

# Run automated setup
./scripts/setup-vps.sh

# Setup SSL
sudo certbot --nginx -d api.dashboard.agenticaiautomation.co
```

### 3. On Cloudflare

**DNS:**
- Add A record: `api.dashboard` → `<VPS IP>` (proxied)

**Pages:**
- Connect GitHub repo
- Build command: `cd web && npm install && npm run build`
- Build output: `web/.next`
- Env var: `NEXT_PUBLIC_API_URL=https://api.dashboard.agenticaiautomation.co`
- Custom domain: `dashboard.agenticaiautomation.co`

---

## Verify

1. Visit: `https://dashboard.agenticaiautomation.co`
2. Login: `Contact@agenticAiAutomation.co` + password from `.env`
3. See dashboard with imported keywords/articles/tasks

---

## Common Issues

**API won't start:**
```bash
sudo journalctl -u dashboard-api -f
# Usually: wrong DATABASE_URL or missing .env
```

**Frontend can't reach API:**
```bash
# Check CORS in api/.env
grep CORS_ORIGINS /var/www/agenticai-dashboard/api/.env
# Must include: https://dashboard.agenticaiautomation.co
```

**Database connection failed:**
```bash
# Test manually
psql -U dashboard_user -d agenticai_dashboard
```

---

## Logs

```bash
# API logs
sudo journalctl -u dashboard-api -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log

# Database logs
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

---

## What Gets Created

- **32 keywords** (4 pillars: BFSI, Logistics, D2C, Coaching)
- **46 articles** (4 pillars + 32 clusters + 10 countries)
- **40+ tasks** (phases 0-6 from SEO_CONTENT_TASKS.md)
- **1 owner user** (Contact@agenticAiAutomation.co)

---

## Next Steps

1. **Change password** (Settings → Users)
2. **Add team members** (SEO, Writers)
3. **Update keywords** with Ubersuggest data
4. **Assign articles** to writers
5. **Track progress** on dashboard

---

Full docs: [README.md](README.md) | [DEPLOY.md](DEPLOY.md) | [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md)
