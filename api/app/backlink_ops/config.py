"""Backlink Ops — configuration.

Every setting is read from the environment so the module can be turned on,
tuned or turned OFF without touching application code. If BACKLINK_OPS_ENABLED
is not "1", the blueprint is never registered and the host application behaves
exactly as it did before this module existed.
"""
import os

def _b(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")

def _csv(name, default=""):
    return [x.strip().lower() for x in os.environ.get(name, default).split(",") if x.strip()]


class Settings:
    # --- master switch -------------------------------------------------
    ENABLED        = _b("BACKLINK_OPS_ENABLED", "0")
    READ_ONLY      = _b("BACKLINK_OPS_READ_ONLY", "0")   # BCP degrade mode: serve, refuse writes

    # --- mount points (namespaced; never collide with existing routes) --
    URL_PREFIX     = os.environ.get("BACKLINK_OPS_URL_PREFIX", "/seo/backlink-ops")
    API_PREFIX     = os.environ.get("BACKLINK_OPS_API_PREFIX", "/api/seo/backlink-ops")

    # --- storage: its OWN sqlite file. The host database is never touched.
    DB_PATH        = os.environ.get("BACKLINK_OPS_DB", "instance/backlink_ops.db")
    BACKUP_DIR     = os.environ.get("BACKLINK_OPS_BACKUP_DIR", "backups/backlink_ops")

    # --- identity / roles ----------------------------------------------
    # Superusers are matched on email (preferred) or username, case-insensitive.
    SUPERUSERS     = _csv("BACKLINK_OPS_SUPERUSERS", "jai.prajapati91@gmail.com")
    # Host roles mapped onto desk roles. See identity.py for the full policy.
    SUPERUSER_ROLES = _csv("BACKLINK_OPS_SUPERUSER_ROLES", "")
    ADMIN_ROLES     = _csv("BACKLINK_OPS_ADMIN_ROLES", "admin,seo_lead,editor,member")
    VIEWER_ROLES    = _csv("BACKLINK_OPS_VIEWER_ROLES", "viewer,readonly,guest")
    # An authenticated user carrying NO role at all: read-only unless told otherwise.
    UNKNOWN_ROLE_IS_ADMIN = _b("BACKLINK_OPS_UNKNOWN_ROLE_IS_ADMIN", "0")

    # How the adapter finds the current user. "module:callable" taking the
    # framework request and returning a user dict — set this when the
    # automatic adapters do not fit. See docs/RUNBOOK.md.
    USER_HOOK      = os.environ.get("BACKLINK_OPS_USER_HOOK", "")
    JWT_SECRET     = os.environ.get("BACKLINK_OPS_JWT_SECRET", "") or \
                     os.environ.get("JWT_SECRET_KEY", "") or \
                     os.environ.get("SECRET_KEY", "")
    JWT_ALGS       = _csv("BACKLINK_OPS_JWT_ALGS", "HS256")
    JWT_COOKIES    = _csv("BACKLINK_OPS_JWT_COOKIES", "access_token,token,jwt,Authorization")

    # Fallback only for environments with no host auth (dev / first boot).
    ALLOW_ANON     = _b("BACKLINK_OPS_ALLOW_ANON", "0")

    # --- AI layer (optional; module degrades to deterministic rules) -----
    AI_PROVIDER    = os.environ.get("BACKLINK_OPS_AI_PROVIDER", "none")   # grok|gemini|anthropic|none
    AI_MODEL       = os.environ.get("BACKLINK_OPS_AI_MODEL", "")
    AI_KEY         = os.environ.get("BACKLINK_OPS_AI_KEY", "")
    AI_BASE_URL    = os.environ.get("BACKLINK_OPS_AI_BASE_URL", "")  # override an endpoint
    AI_TIMEOUT     = float(os.environ.get("BACKLINK_OPS_AI_TIMEOUT", "25"))
    AI_DAILY_CAP   = int(os.environ.get("BACKLINK_OPS_AI_DAILY_CAP", "200"))

    # --- observability --------------------------------------------------
    LOG_PREFIX     = os.environ.get("BACKLINK_OPS_LOG_PREFIX", "backlink-ops")
    FEATURE_LOG    = os.environ.get("BACKLINK_OPS_FEATURE_LOG", "docs/FEATURE_LOG.md")

    VERSION        = "1.0.0"
    SCHEMA_VERSION = 1


settings = Settings()
