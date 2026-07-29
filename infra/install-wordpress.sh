#!/bin/bash
# Provision WordPress at /var/www/blog for agenticaiautomation.co/blog/*
#
# Run as root on the VPS:
#   bash /var/www/agenticai-dashboard/infra/install-wordpress.sh
#
# Idempotent: re-running skips anything already in place. Every generated
# secret is written to /root/wordpress-install-secrets.txt (chmod 600) so the
# credentials file generator can pick them up.
set -euo pipefail

BLOG_DIR=/var/www/blog
SITE_URL="https://agenticaiautomation.co/blog"
DB_NAME=agenticai_blog
DB_USER=agenticai_blog
WP_ADMIN_USER=jai_admin
WP_ADMIN_EMAIL="${JAI_ADMIN_EMAIL:-contact@agenticaiautomation.co}"
SECRETS_FILE=/root/wordpress-install-secrets.txt

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run this as root." >&2
    exit 1
  fi
}

gen_password() {
  # 20 chars, alphanumeric plus a fixed symbol set. Avoids shell/SQL quoting
  # hazards while staying well above the 12-character policy minimum.
  tr -dc 'A-Za-z0-9!@#%^&*_+-' </dev/urandom | head -c 20
  echo
}

require_root

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  mariadb-server \
  php-fpm php-mysql php-curl php-gd php-mbstring php-xml php-zip php-intl \
  curl unzip

PHP_VERSION=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')
PHP_SOCK="/run/php/php${PHP_VERSION}-fpm.sock"
echo "    PHP ${PHP_VERSION}, socket ${PHP_SOCK}"

echo "==> Ensuring MariaDB is running"
systemctl enable --now mariadb

# --- Database -------------------------------------------------------------
if mysql -e "USE ${DB_NAME}" 2>/dev/null; then
  echo "==> Database ${DB_NAME} already exists, leaving it alone"
  DB_PASSWORD=$(grep -oP '(?<=^WP_DB_PASSWORD=).*' "$SECRETS_FILE" 2>/dev/null || true)
  if [ -z "${DB_PASSWORD}" ]; then
    echo "ERROR: ${DB_NAME} exists but its password is not in ${SECRETS_FILE}." >&2
    echo "       Recover it from ${BLOG_DIR}/wp-config.php before re-running." >&2
    exit 1
  fi
else
  DB_PASSWORD=$(gen_password)
  echo "==> Creating database ${DB_NAME}"
  mysql <<SQL
CREATE DATABASE ${DB_NAME} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
fi

# --- WP-CLI ---------------------------------------------------------------
if ! command -v wp >/dev/null 2>&1; then
  echo "==> Installing WP-CLI"
  curl -fsSL -o /usr/local/bin/wp \
    https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar
  chmod +x /usr/local/bin/wp
fi

wpcli() { sudo -u www-data -- wp --path="${BLOG_DIR}" "$@"; }

# --- Core -----------------------------------------------------------------
mkdir -p "${BLOG_DIR}"
chown www-data:www-data "${BLOG_DIR}"

if [ ! -f "${BLOG_DIR}/wp-load.php" ]; then
  echo "==> Downloading WordPress core"
  wpcli core download
fi

if [ ! -f "${BLOG_DIR}/wp-config.php" ]; then
  echo "==> Writing wp-config.php"
  wpcli config create \
    --dbname="${DB_NAME}" \
    --dbuser="${DB_USER}" \
    --dbpass="${DB_PASSWORD}" \
    --dbhost=localhost \
    --skip-check
  # Subfolder install: WordPress must know it lives under /blog.
  wpcli config set WP_HOME "${SITE_URL}" --type=constant
  wpcli config set WP_SITEURL "${SITE_URL}" --type=constant
  # The dashboard publishes over the REST API; the file editor is an
  # unnecessary remote-code-execution surface.
  wpcli config set DISALLOW_FILE_EDIT true --raw --type=constant
  wpcli config set FORCE_SSL_ADMIN true --raw --type=constant
fi

if wpcli core is-installed 2>/dev/null; then
  echo "==> WordPress is already installed"
  WP_ADMIN_PASSWORD="(unchanged — see ${SECRETS_FILE})"
else
  WP_ADMIN_PASSWORD=$(gen_password)
  echo "==> Installing WordPress"
  wpcli core install \
    --url="${SITE_URL}" \
    --title="Agentic AI Automation Blog" \
    --admin_user="${WP_ADMIN_USER}" \
    --admin_password="${WP_ADMIN_PASSWORD}" \
    --admin_email="${WP_ADMIN_EMAIL}" \
    --skip-email
fi

echo "==> Setting permalinks to /blog/%postname%/"
wpcli rewrite structure '/%postname%/' --hard
wpcli option update blog_public 1

# --- Plugins --------------------------------------------------------------
echo "==> Installing RankMath (Article + FAQ + BreadcrumbList schema)"
wpcli plugin install seo-by-rank-math --activate || \
  echo "    WARNING: RankMath install failed — install it from wp-admin."

# --- Editorial author -----------------------------------------------------
if ! wpcli user get editorial >/dev/null 2>&1; then
  echo "==> Creating the editorial author profile"
  EDITORIAL_PASSWORD=$(gen_password)
  wpcli user create editorial "editorial@agenticaiautomation.co" \
    --role=author \
    --display_name="Agentic AI Automation Editorial" \
    --user_pass="${EDITORIAL_PASSWORD}"
else
  EDITORIAL_PASSWORD="(unchanged)"
fi

# --- Application password for the dashboard --------------------------------
echo "==> Creating a REST application password for the dashboard"
WP_APP_PASSWORD=$(wpcli user application-password create "${WP_ADMIN_USER}" \
  agenticai-dashboard --porcelain 2>/dev/null || echo "")
if [ -z "${WP_APP_PASSWORD}" ]; then
  echo "    WARNING: could not create an application password automatically."
  echo "    Create one in wp-admin > Users > ${WP_ADMIN_USER} > Application Passwords."
fi

chown -R www-data:www-data "${BLOG_DIR}"
find "${BLOG_DIR}" -type d -exec chmod 755 {} \;
find "${BLOG_DIR}" -type f -exec chmod 644 {} \;
chmod 640 "${BLOG_DIR}/wp-config.php"

# --- Record the secrets ----------------------------------------------------
umask 077
cat > "${SECRETS_FILE}" <<EOF
# Generated by install-wordpress.sh on $(date -Is)
WP_DB_NAME=${DB_NAME}
WP_DB_USER=${DB_USER}
WP_DB_PASSWORD=${DB_PASSWORD}
WP_ADMIN_USER=${WP_ADMIN_USER}
WP_ADMIN_EMAIL=${WP_ADMIN_EMAIL}
WP_ADMIN_PASSWORD=${WP_ADMIN_PASSWORD}
WP_EDITORIAL_PASSWORD=${EDITORIAL_PASSWORD}
WP_APP_USER=${WP_ADMIN_USER}
WP_APP_PASSWORD=${WP_APP_PASSWORD}
PHP_FPM_SOCKET=${PHP_SOCK}
EOF
chmod 600 "${SECRETS_FILE}"

cat <<EOF

==> WordPress install complete.

Secrets written to ${SECRETS_FILE} (chmod 600).

Next steps, in order:
  1. cp infra/nginx-blog-subfolder.conf /etc/nginx/snippets/blog-subfolder.conf
     Confirm the fastcgi_pass line matches ${PHP_SOCK}.
  2. Add this line inside the agenticaiautomation.co server block:
       include /etc/nginx/snippets/blog-subfolder.conf;
  3. nginx -t && systemctl reload nginx
  4. Add to /var/www/agenticai-dashboard/api/.env:
       WP_BASE_URL=${SITE_URL}
       WP_APP_USER=${WP_ADMIN_USER}
       WP_APP_PASSWORD=<the WP_APP_PASSWORD value from ${SECRETS_FILE}>
  5. systemctl restart dashboard-api
  6. Verify: GET https://api.dashboard.agenticaiautomation.co/api/seo/health/integrations
  7. Prove the round trip:
       POST /api/seo/health/wordpress-hello-world
EOF
