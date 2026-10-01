"""Invoice Desk — configuration.

Same contract as Backlink Ops: every switch is an environment variable, so the
feature can be turned on, tuned or turned OFF without touching code. If
INVOICE_DESK_ENABLED is not "1", nothing is mounted and the dashboard behaves
exactly as it did before this module existed.
"""
import os


def _b(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _csv(name, default=""):
    return [x.strip().lower() for x in os.environ.get(name, default).split(",") if x.strip()]


class Settings:
    # --- master switch + BCP degrade mode --------------------------------
    ENABLED     = _b("INVOICE_DESK_ENABLED", "0")
    READ_ONLY   = _b("INVOICE_DESK_READ_ONLY", "0")    # serve + download, refuse writes

    # --- mount points (namespaced; collision-guarded at register time) ---
    URL_PREFIX  = os.environ.get("INVOICE_DESK_URL_PREFIX", "/invoices")
    API_PREFIX  = os.environ.get("INVOICE_DESK_API_PREFIX", "/api/invoices")
    # Absolute origin used when building the shareable fill link.
    PUBLIC_BASE = os.environ.get("INVOICE_DESK_PUBLIC_BASE",
                                 "https://dashboard.agenticaiautomation.co").rstrip("/")

    # --- storage: its OWN sqlite file; the host Postgres is never touched -
    DB_PATH     = os.environ.get("INVOICE_DESK_DB", "instance/invoice_desk.db")
    BACKUP_DIR  = os.environ.get("INVOICE_DESK_BACKUP_DIR", "backups/invoice_desk")
    BACKUP_KEEP = int(os.environ.get("INVOICE_DESK_BACKUP_KEEP", "90"))

    # --- identity --------------------------------------------------------
    # Money is superuser-only: only these emails can see, edit or issue.
    SUPERUSERS  = _csv("INVOICE_DESK_SUPERUSERS",
                       "contact@agenticaiautomation.co,jai.prajapati91@gmail.com")
    # "module:callable(request) -> dict|None", must never raise. Defaults to
    # the same non-raising wrapper Backlink Ops uses (a host file, not part of
    # that module — it keeps working if Backlink Ops is switched off).
    USER_HOOK   = os.environ.get("INVOICE_DESK_USER_HOOK",
                                 "app.backlink_ops_hook:get_user_or_none")
    TOKEN_STORAGE_KEY = os.environ.get("INVOICE_DESK_TOKEN_STORAGE_KEY", "access_token")
    LOGIN_URL   = os.environ.get("INVOICE_DESK_LOGIN_URL", "/login/")

    # --- public fill links -------------------------------------------------
    LINK_DAYS   = int(os.environ.get("INVOICE_DESK_LINK_DAYS", "14"))
    # Max public submissions per IP per hour (spam brake, in-memory).
    PUBLIC_RATE = int(os.environ.get("INVOICE_DESK_PUBLIC_RATE", "10"))

    LOG_PREFIX  = "invoice-desk"
    VERSION     = "1.0.0"
    SCHEMA_VERSION = 1


settings = Settings()
