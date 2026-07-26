#!/bin/bash
# Pre-deployment verification script
# Run this locally before deploying

echo "===== Pre-Deployment Verification ====="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

echo "Checking required files..."

# Check backend files
if [ -f "api/requirements.txt" ]; then
  echo -e "${GREEN}✓${NC} api/requirements.txt"
else
  echo -e "${RED}✗${NC} api/requirements.txt missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "api/app/main.py" ]; then
  echo -e "${GREEN}✓${NC} api/app/main.py"
else
  echo -e "${RED}✗${NC} api/app/main.py missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "api/app/seed.py" ]; then
  echo -e "${GREEN}✓${NC} api/app/seed.py"
else
  echo -e "${RED}✗${NC} api/app/seed.py missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "api/alembic/versions/001_initial_schema.py" ]; then
  echo -e "${GREEN}✓${NC} api/alembic/versions/001_initial_schema.py"
else
  echo -e "${RED}✗${NC} Migration file missing"
  ERRORS=$((ERRORS+1))
fi

# Check seed data
if [ -f "api/seed-data/SEO_CONTENT_TASKS.md" ]; then
  echo -e "${GREEN}✓${NC} api/seed-data/SEO_CONTENT_TASKS.md"
else
  echo -e "${RED}✗${NC} SEO_CONTENT_TASKS.md missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "api/seed-data/keyword-cluster.md" ]; then
  echo -e "${GREEN}✓${NC} api/seed-data/keyword-cluster.md"
else
  echo -e "${RED}✗${NC} keyword-cluster.md missing"
  ERRORS=$((ERRORS+1))
fi

# Check frontend files
if [ -f "web/package.json" ]; then
  echo -e "${GREEN}✓${NC} web/package.json"
else
  echo -e "${RED}✗${NC} web/package.json missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "web/app/login/page.tsx" ]; then
  echo -e "${GREEN}✓${NC} web/app/login/page.tsx"
else
  echo -e "${RED}✗${NC} Login page missing"
  ERRORS=$((ERRORS+1))
fi

# Check infrastructure files
if [ -f "infra/dashboard-api.service" ]; then
  echo -e "${GREEN}✓${NC} infra/dashboard-api.service"
else
  echo -e "${RED}✗${NC} Systemd service file missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "infra/nginx-dashboard.conf" ]; then
  echo -e "${GREEN}✓${NC} infra/nginx-dashboard.conf"
else
  echo -e "${RED}✗${NC} Nginx config missing"
  ERRORS=$((ERRORS+1))
fi

# Check documentation
if [ -f "README.md" ]; then
  echo -e "${GREEN}✓${NC} README.md"
else
  echo -e "${RED}✗${NC} README.md missing"
  ERRORS=$((ERRORS+1))
fi

if [ -f "DEPLOY.md" ]; then
  echo -e "${GREEN}✓${NC} DEPLOY.md"
else
  echo -e "${RED}✗${NC} DEPLOY.md missing"
  ERRORS=$((ERRORS+1))
fi

echo ""
echo "Checking .env.example..."
if [ -f "api/.env.example" ]; then
  if grep -q "DATABASE_URL" api/.env.example && \
     grep -q "JWT_SECRET_KEY" api/.env.example && \
     grep -q "INITIAL_OWNER_PASSWORD" api/.env.example; then
    echo -e "${GREEN}✓${NC} .env.example has required variables"
  else
    echo -e "${YELLOW}⚠${NC} .env.example missing some required variables"
  fi
else
  echo -e "${RED}✗${NC} .env.example missing"
  ERRORS=$((ERRORS+1))
fi

echo ""
echo "Checking .gitignore..."
if [ -f ".gitignore" ]; then
  if grep -q "venv" .gitignore && \
     grep -q ".env" .gitignore && \
     grep -q "node_modules" .gitignore; then
    echo -e "${GREEN}✓${NC} .gitignore configured correctly"
  else
    echo -e "${YELLOW}⚠${NC} .gitignore may be incomplete"
  fi
else
  echo -e "${RED}✗${NC} .gitignore missing"
  ERRORS=$((ERRORS+1))
fi

echo ""
echo "Checking git status..."
if [ -d ".git" ]; then
  echo -e "${GREEN}✓${NC} Git repository initialized"

  # Check for uncommitted changes
  if [ -n "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}⚠${NC} You have uncommitted changes:"
    git status --short
    echo ""
    echo -e "${YELLOW}Commit these before deploying!${NC}"
  else
    echo -e "${GREEN}✓${NC} All changes committed"
  fi

  # Check for remote
  if git remote -v | grep -q origin; then
    echo -e "${GREEN}✓${NC} Git remote 'origin' configured"
    git remote -v | head -2
  else
    echo -e "${YELLOW}⚠${NC} No git remote configured"
    echo "   Add with: git remote add origin <your-repo-url>"
  fi
else
  echo -e "${RED}✗${NC} Not a git repository"
  ERRORS=$((ERRORS+1))
fi

echo ""
echo "File count summary:"
PY_FILES=$(find api -name "*.py" 2>/dev/null | wc -l)
TSX_FILES=$(find web -name "*.tsx" -o -name "*.ts" 2>/dev/null | wc -l)
echo "  Python files: $PY_FILES"
echo "  TypeScript files: $TSX_FILES"

echo ""
echo "======================================"
if [ $ERRORS -eq 0 ]; then
  echo -e "${GREEN}✅ Pre-deployment check PASSED${NC}"
  echo ""
  echo "Next steps:"
  echo "1. git remote add origin <your-repo-url>"
  echo "2. git push -u origin main"
  echo "3. SSH to VPS and follow DEPLOY.md"
  exit 0
else
  echo -e "${RED}❌ Pre-deployment check FAILED${NC}"
  echo "   Found $ERRORS error(s)"
  echo "   Fix these issues before deploying"
  exit 1
fi
