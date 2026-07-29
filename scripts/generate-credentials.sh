#!/bin/bash
# Generate /var/www/agenticai-dashboard/CREDENTIALS_JAI.md (chmod 600, root only).
#
# Run as root on the VPS, AFTER install-wordpress.sh and after the dashboard
# API is up:
#   bash /var/www/agenticai-dashboard/scripts/generate-credentials.sh
#
# What it does:
#   - creates or resets Jai's dashboard admin account with a fresh 16-char
#     password, flagged must_change_password
#   - reads the WordPress secrets written by install-wordpress.sh
#   - writes both into one root-only file
#
# It never prints secrets to stdout. Read the file, then delete it.
set -euo pipefail

APP_DIR=/var/www/agenticai-dashboard
OUTPUT="${APP_DIR}/CREDENTIALS_JAI.md"
WP_SECRETS=/root/wordpress-install-secrets.txt
JAI_EMAIL="${JAI_ADMIN_EMAIL:-contact@agenticaiautomation.co}"
PYTHON="${APP_DIR}/api/venv/bin/python"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: run this as root." >&2
  exit 1
fi

if [ ! -x "$PYTHON" ]; then
  echo "ERROR: ${PYTHON} not found. Create the API virtualenv first." >&2
  exit 1
fi

echo "==> Provisioning the dashboard admin account"
DASHBOARD_PASSWORD=$(cd "${APP_DIR}/api" && "$PYTHON" - "$JAI_EMAIL" <<'PY'
import sys

from app.auth import generate_password, get_password_hash
from app.database import SessionLocal
from app.models import User

email = sys.argv[1].lower()
password = generate_password(16)

db = SessionLocal()
try:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            full_name="Jai Prajapati",
            role="admin",
            password_hash=get_password_hash(password),
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
    else:
        user.role = "admin"
        user.is_active = True
        user.password_hash = get_password_hash(password)
        user.must_change_password = True
        # Invalidate any live session so the new password is the only way in.
        user.last_activity_at = None
    db.commit()
finally:
    db.close()

# Only the password reaches stdout; everything else goes to stderr.
print(password)
PY
)

if [ -z "$DASHBOARD_PASSWORD" ]; then
  echo "ERROR: failed to provision the dashboard admin account." >&2
  exit 1
fi

# --- WordPress secrets ------------------------------------------------------
read_secret() { grep -oP "(?<=^$1=).*" "$WP_SECRETS" 2>/dev/null || echo ""; }

if [ -r "$WP_SECRETS" ]; then
  WP_ADMIN_USER=$(read_secret WP_ADMIN_USER)
  WP_ADMIN_PASSWORD=$(read_secret WP_ADMIN_PASSWORD)
  WP_APP_PASSWORD=$(read_secret WP_APP_PASSWORD)
  WP_EDITORIAL_PASSWORD=$(read_secret WP_EDITORIAL_PASSWORD)
else
  WP_ADMIN_USER="(not provisioned)"
  WP_ADMIN_PASSWORD="(run infra/install-wordpress.sh first)"
  WP_APP_PASSWORD="(run infra/install-wordpress.sh first)"
  WP_EDITORIAL_PASSWORD="(run infra/install-wordpress.sh first)"
fi

umask 077
cat > "$OUTPUT" <<EOF
# Credentials — Jai

Generated $(date -Is) on $(hostname).
File mode 600, owned by root. **Read it, store the values in your password
manager, then delete this file.**

---

## 1. Dashboard admin

- URL: https://dashboard.agenticaiautomation.co/dashboard/
- Email: \`${JAI_EMAIL}\`
- Password: \`${DASHBOARD_PASSWORD}\`
- Role: admin
- Forced password change on first login: **yes** — you land on
  /account/password before the dashboard.
- Session timeout: 8 hours idle, enforced server-side.

### 2FA

TOTP columns (\`totp_secret\`, \`totp_enabled\`) exist on the users table and
\`pyotp\` is installed, but the enrolment endpoint and QR flow are **not built
yet** — that is Week 4 work. Until then the account is password-only. Do not
assume 2FA is protecting this login.

---

## 2. WordPress admin

- URL: https://agenticaiautomation.co/blog/wp-admin/
- Username: \`${WP_ADMIN_USER}\`
- Password: \`${WP_ADMIN_PASSWORD}\`
- Change it on first login (WordPress does not force this itself).

### REST application password (used by the dashboard)

- \`WP_APP_USER=${WP_ADMIN_USER}\`
- \`WP_APP_PASSWORD=${WP_APP_PASSWORD}\`

These belong in \`${APP_DIR}/api/.env\`, not in wp-admin. This is a separate
credential from the login password above — revoking one does not affect the
other.

### Editorial author profile

- Username: \`editorial\`
- Display name: Agentic AI Automation Editorial
- Password: \`${WP_EDITORIAL_PASSWORD}\`

Team-published articles carry this byline, so individual team members are not
named on the public blog.

---

## 3. SEO team logins

Not created — real email addresses are still needed.

To activate each one:

1. Sign in to the dashboard as admin.
2. Users → Add user.
3. Role \`seo_lead\`; leave the vertical and country scopes empty for full access.
4. Leave the password field blank. The API generates a compliant 16-character
   password and shows it **once**; send it to the person over a channel they
   already control.

| Placeholder | Email | Status |
| --- | --- | --- |
| seo_lead_1 | TBD | not created |
| seo_lead_2 | TBD | not created |

---

## Rotating any of this

- Dashboard password: Users → Reset password (also ends their live sessions).
- WordPress login: wp-admin → Users → Profile.
- WP application password: wp-admin → Users → ${WP_ADMIN_USER} → Application
  Passwords → revoke and re-issue, then update \`api/.env\` and restart
  \`dashboard-api\`.
EOF

chmod 600 "$OUTPUT"
chown root:root "$OUTPUT"

echo "==> Wrote ${OUTPUT} (chmod 600, root only)."
echo "    Read it, save the values elsewhere, then: rm ${OUTPUT}"
