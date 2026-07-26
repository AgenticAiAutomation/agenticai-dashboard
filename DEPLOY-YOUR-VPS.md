# Deployment for Your VPS - Step by Step

**VPS IP:** 187.127.173.209  
**SSH User:** root  
**OS:** Ubuntu

---

## STEP 1: Push to GitHub (Local - Windows)

First, create GitHub repository:
1. Go to https://github.com/new
2. Name: `agenticai-dashboard`
3. Private repository
4. Don't initialize with README
5. Create repository
6. Copy the URL

Then push code:

```powershell
cd C:\Users\hp\Documents\agenticai-dashboard

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/agenticai-dashboard.git

# Push
git push -u origin main
```

✅ **Checkpoint:** Code visible on GitHub

---

## STEP 2: Connect to VPS

Open PowerShell and connect:

```powershell
ssh root@187.127.173.209
# Password: HeroHonda@8508
```

Once connected, verify Ubuntu version:

```bash
lsb_release -a
```

---

## STEP 3: Install Prerequisites (if needed)

```bash
# Update system
apt update

# Check Python version (need 3.12 or 3.10+)
python3 --version

# If Python is old, install Python 3.12
# apt install python3.12 python3.12-venv python3-pip -y

# Check PostgreSQL
systemctl status postgresql

# If not installed:
# apt install postgresql postgresql-contrib -y

# Check nginx
nginx -v

# If not installed:
# apt install nginx -y

# Install certbot
apt install certbot python3-certbot-nginx -y
```

---

## STEP 4: Create Database

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL prompt, run:
CREATE DATABASE agenticai_dashboard;
CREATE USER dashboard_user WITH PASSWORD 'SecureDashboard2026!';
GRANT ALL PRIVILEGES ON DATABASE agenticai_dashboard TO dashboard_user;
ALTER DATABASE agenticai_dashboard OWNER TO dashboard_user;
\q

# Test connection
psql -U dashboard_user -d agenticai_dashboard -h localhost
# Password: SecureDashboard2026!
# Type \q to exit
```

✅ **Checkpoint:** Database created and accessible

---

## STEP 5: Clone Repository

```bash
cd /var/www

# Clone from GitHub (replace YOUR_USERNAME)
git clone https://github.com/YOUR_USERNAME/agenticai-dashboard.git

# If directory exists from old deployment:
# rm -rf agenticai-dashboard
# git clone ...

cd agenticai-dashboard

# Verify files
ls -la
# Should see: api/, web/, infra/, README.md, etc.
```

✅ **Checkpoint:** Code cloned to `/var/www/agenticai-dashboard`

---

## STEP 6: Configure Backend Environment

```bash
cd /var/www/agenticai-dashboard/api

# Create .env file
cp .env.example .env

# Generate JWT secret
JWT_SECRET=$(openssl rand -hex 32)
echo "Generated JWT Secret: $JWT_SECRET"

# Edit .env
nano .env
```

**Update these values in .env:**

```env
DATABASE_URL=postgresql://dashboard_user:SecureDashboard2026!@localhost/agenticai_dashboard
JWT_SECRET_KEY=<paste the JWT secret from above>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
INITIAL_OWNER_EMAIL=Contact@agenticAiAutomation.co
INITIAL_OWNER_PASSWORD=AgenticDash2026!
CORS_ORIGINS=https://dashboard.agenticaiautomation.co,http://localhost:3000
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## STEP 7: Install Python Dependencies

```bash
cd /var/www/agenticai-dashboard/api

# Create virtual environment
python3 -m venv venv

# Activate
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies (takes 2-3 minutes)
pip install -r requirements.txt
```

✅ **Checkpoint:** Dependencies installed

---

## STEP 8: Run Migrations

```bash
cd /var/www/agenticai-dashboard/api
source venv/bin/activate

# Run migrations
alembic upgrade head
```

Expected output: `Running upgrade  -> 001, initial_schema`

✅ **Checkpoint:** Database schema created

---

## STEP 9: Seed Database

```bash
# Still in api/ directory with venv activated
python -m app.seed
```

**Expected output:**
```
✓ Created owner user: Contact@agenticAiAutomation.co
✓ Imported 40+ tasks from SEO_CONTENT_TASKS.md
✓ Imported 32 keywords from keyword-cluster.md
✓ Created 46 article placeholders
```

✅ **Checkpoint:** Data imported successfully

---

## STEP 10: Test API Manually

```bash
# Start API manually (to test)
uvicorn app.main:app --host 127.0.0.1 --port 5003
```

Open a **NEW SSH session** (keep first one running) and test:

```bash
ssh root@187.127.173.209

curl http://127.0.0.1:5003/health
# Should return: {"status":"healthy"}

curl http://127.0.0.1:5003/
# Should return: {"message":"AgenticAI Dashboard API","version":"1.0.0"}
```

Go back to **first SSH session** and stop the test server: `Ctrl+C`

✅ **Checkpoint:** API working locally

---

## STEP 11: Setup Systemd Service

```bash
# Copy service file
cp /var/www/agenticai-dashboard/infra/dashboard-api.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable dashboard-api

# Start service
systemctl start dashboard-api

# Check status
systemctl status dashboard-api
```

Should show: `Active: active (running)`

Test again:

```bash
curl http://127.0.0.1:5003/health
```

✅ **Checkpoint:** Service running

---

## STEP 12: Configure Nginx

```bash
# Copy nginx config
cp /var/www/agenticai-dashboard/infra/nginx-dashboard.conf /etc/nginx/sites-available/dashboard

# IMPORTANT: Edit to temporarily remove SSL (we'll add it after certbot)
nano /etc/nginx/sites-available/dashboard
```

**Modify the file to look like this (temporarily):**

```nginx
server {
    listen 80;
    server_name api.dashboard.agenticaiautomation.co;

    location / {
        proxy_pass http://127.0.0.1:5003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:5003/health;
        access_log off;
    }
}
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

```bash
# Create symlink
ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/

# Test nginx config
nginx -t

# Reload nginx
systemctl reload nginx
```

✅ **Checkpoint:** Nginx configured

---

## STEP 13: Configure DNS (Do this in Cloudflare)

1. Go to Cloudflare Dashboard
2. Select domain: `agenticaiautomation.co`
3. Go to **DNS** → **Records**
4. Click **Add record**

**Add A Record:**
- Type: `A`
- Name: `api.dashboard`
- IPv4 address: `187.127.173.209`
- Proxy status: **Proxied** (orange cloud)
- TTL: Auto

5. Click **Save**

Wait 2-3 minutes for DNS propagation.

**Test DNS:**

```bash
nslookup api.dashboard.agenticaiautomation.co
```

Should return: `187.127.173.209`

**Test HTTP (before SSL):**

```bash
curl http://api.dashboard.agenticaiautomation.co/health
```

✅ **Checkpoint:** DNS working

---

## STEP 14: Get SSL Certificate

```bash
# Get certificate from Let's Encrypt
certbot --nginx -d api.dashboard.agenticaiautomation.co
```

**Follow prompts:**
- Enter email: `jai.prajapati91@gmail.com`
- Agree to terms: `Y`
- Share email: `N` (optional)
- Redirect HTTP to HTTPS: `2` (Yes, recommended)

Certbot will automatically update nginx config.

**Test SSL:**

```bash
curl https://api.dashboard.agenticaiautomation.co/health
```

Should return: `{"status":"healthy"}`

**Test auto-renewal:**

```bash
certbot renew --dry-run
```

✅ **Checkpoint:** SSL working

---

## STEP 15: Deploy Frontend to Cloudflare Pages

1. Go to **Cloudflare Dashboard**
2. Click **Pages** → **Create a project**
3. Click **Connect to Git** → **GitHub**
4. Authorize Cloudflare (if first time)
5. Select repository: `YOUR_USERNAME/agenticai-dashboard`
6. Click **Begin setup**

**Configure build:**
- Project name: `agenticai-dashboard`
- Production branch: `main`
- Framework preset: **Next.js**
- Build command: `cd web && npm install && npm run build`
- Build output directory: `web/.next`
- Root directory: (leave blank)

**Environment variables:**

Click **Add variable**:
- Variable name: `NEXT_PUBLIC_API_URL`
- Value: `https://api.dashboard.agenticaiautomation.co`

7. Click **Save and Deploy**

Wait 5-10 minutes for build to complete.

✅ **Checkpoint:** Frontend deployed to Cloudflare Pages

---

## STEP 16: Add Custom Domain

Once build completes:

1. In Cloudflare Pages project
2. Go to **Custom domains**
3. Click **Set up a custom domain**
4. Enter: `dashboard.agenticaiautomation.co`
5. Click **Continue**

Cloudflare will automatically configure DNS.

Wait 2-3 minutes.

**Visit:** `https://dashboard.agenticaiautomation.co`

You should see the **login page**!

✅ **Checkpoint:** Frontend accessible

---

## STEP 17: Test Login

1. Go to: `https://dashboard.agenticaiautomation.co`
2. Login with:
   - **Email:** `Contact@agenticAiAutomation.co`
   - **Password:** `AgenticDash2026!` (from your .env)

3. **Verify all screens:**
   - Dashboard - shows keyword/article counts
   - Keywords - table with imported data
   - Articles - kanban board
   - Countries - 10 country pages
   - Tasks - imported tasks
   - Settings/Users - user management

✅ **Checkpoint:** All screens working

---

## STEP 18: Post-Deployment

### Change Initial Password

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
user.password_hash = get_password_hash("NewSecurePassword2026!")
db.commit()
print("✓ Password updated to: NewSecurePassword2026!")
EOF
```

### Create Database Backup

```bash
# Create backup directory
mkdir -p ~/backups

# Create backup
pg_dump -U dashboard_user agenticai_dashboard > ~/backups/dashboard-backup-$(date +%Y%m%d).sql

# Verify backup
ls -lh ~/backups/
```

✅ **Checkpoint:** System secured

---

## ✅ DEPLOYMENT COMPLETE!

**Your dashboard is live at:**
- **Frontend:** https://dashboard.agenticaiautomation.co
- **API:** https://api.dashboard.agenticaiautomation.co

**Login credentials:**
- Email: `Contact@agenticAiAutomation.co`
- Password: `NewSecurePassword2026!` (or your chosen password)

---

## Maintenance Commands

```bash
# View API logs
journalctl -u dashboard-api -f

# Restart API
systemctl restart dashboard-api

# Check status
systemctl status dashboard-api

# Update code from GitHub
cd /var/www/agenticai-dashboard
git pull origin main
systemctl restart dashboard-api

# Database backup
pg_dump -U dashboard_user agenticai_dashboard > ~/backups/dashboard-$(date +%Y%m%d).sql
```

---

## Troubleshooting

**API not responding:**
```bash
systemctl status dashboard-api
journalctl -u dashboard-api -n 50
```

**Database connection failed:**
```bash
psql -U dashboard_user -d agenticai_dashboard
```

**Frontend can't reach API:**
- Check CORS in `/var/www/agenticai-dashboard/api/.env`
- Should include: `https://dashboard.agenticaiautomation.co`

---

**🎉 Congratulations! Your SEO dashboard is deployed and ready to use!**
