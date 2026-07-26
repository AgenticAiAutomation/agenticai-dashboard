#!/bin/bash
# Quick setup script for VPS deployment
# Run this on the VPS after transferring files

set -e

echo "===== AgenticAI Dashboard - VPS Setup ====="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then
  echo -e "${YELLOW}Warning: Don't run as root. Run as your normal user with sudo access.${NC}"
  exit 1
fi

echo -e "${GREEN}[1/8] Creating database...${NC}"
sudo -u postgres psql <<EOF
CREATE DATABASE agenticai_dashboard;
CREATE USER dashboard_user WITH PASSWORD 'YourSecurePassword123';
GRANT ALL PRIVILEGES ON DATABASE agenticai_dashboard TO dashboard_user;
EOF
echo "✓ Database created"

echo ""
echo -e "${GREEN}[2/8] Setting up Python environment...${NC}"
cd /var/www/agenticai-dashboard/api
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
echo "✓ Python dependencies installed"

echo ""
echo -e "${GREEN}[3/8] Configuring environment...${NC}"
if [ ! -f .env ]; then
  echo -e "${YELLOW}⚠ .env file not found. Please create it manually:${NC}"
  echo "  cp .env.example .env"
  echo "  nano .env"
  echo "  # Update DATABASE_URL password, JWT_SECRET_KEY, INITIAL_OWNER_PASSWORD"
  exit 1
fi

# Generate JWT secret if placeholder exists
if grep -q "your_jwt_secret_key_here" .env; then
  JWT_SECRET=$(openssl rand -hex 32)
  sed -i "s/your_jwt_secret_key_here_generate_with_openssl_rand_hex_32/$JWT_SECRET/" .env
  echo "✓ Generated JWT secret key"
fi

echo ""
echo -e "${GREEN}[4/8] Running database migrations...${NC}"
venv/bin/alembic upgrade head
echo "✓ Migrations complete"

echo ""
echo -e "${GREEN}[5/8] Seeding database...${NC}"
venv/bin/python -m app.seed
echo "✓ Database seeded"

echo ""
echo -e "${GREEN}[6/8] Setting up systemd service...${NC}"
sudo cp /var/www/agenticai-dashboard/infra/dashboard-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard-api
sudo systemctl start dashboard-api
sleep 2
sudo systemctl status dashboard-api --no-pager
echo "✓ Service started"

echo ""
echo -e "${GREEN}[7/8] Configuring nginx...${NC}"
sudo cp /var/www/agenticai-dashboard/infra/nginx-dashboard.conf /etc/nginx/sites-available/dashboard
sudo ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
echo "✓ Nginx configured"

echo ""
echo -e "${GREEN}[8/8] Testing API...${NC}"
sleep 2
curl -f http://127.0.0.1:5003/health && echo "" || echo "⚠ API health check failed"

echo ""
echo -e "${GREEN}===== Setup Complete! =====${NC}"
echo ""
echo "Next steps:"
echo "1. Set up DNS A record: api.dashboard.agenticaiautomation.co → $(curl -s ifconfig.me)"
echo "2. Run SSL: sudo certbot --nginx -d api.dashboard.agenticaiautomation.co"
echo "3. Deploy frontend to Cloudflare Pages"
echo ""
echo "Initial login:"
echo "  Email: Contact@agenticAiAutomation.co"
echo "  Password: (check .env INITIAL_OWNER_PASSWORD)"
echo ""
echo "View logs: sudo journalctl -u dashboard-api -f"
