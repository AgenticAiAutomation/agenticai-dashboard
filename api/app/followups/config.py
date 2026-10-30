"""Follow-ups — configuration (environment only, like every desk)."""
import os


def _b(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _csv(name, default=""):
    return [x.strip().lower() for x in os.environ.get(name, default).split(",") if x.strip()]


class Settings:
    ENABLED    = _b("FEATURE_FOLLOWUPS", "0")
    READ_ONLY  = _b("FOLLOWUPS_READ_ONLY", "0")
    API_PREFIX = "/api/followups"
    DB_PATH    = os.environ.get("FOLLOWUPS_DB", "instance/followups.db")
    # Who may use it: these emails, plus the marketing team the owner lists (fu_access).
    # A dashboard role alone gives no access since 31 Oct 2026 (SEO and writers don't need it).
    SUPERUSERS = _csv("FOLLOWUPS_SUPERUSERS",
                      os.environ.get("BACKLINK_OPS_SUPERUSERS",
                                     "contact@agenticaiautomation.co"))
    ROLES      = _csv("FOLLOWUPS_ROLES", "")
    USER_HOOK  = os.environ.get("FOLLOWUPS_USER_HOOK", "app.backlink_ops_hook:get_user_or_none")
    # The four follow-ups Jai listed on 22 Oct 2026 are loaded once into an
    # empty database. 0 = start empty.
    SEED       = _b("FOLLOWUPS_SEED", "1")
    VERSION    = "1.1.0"
    REMIND_DAYS = int(os.environ.get("FOLLOWUPS_PAYMENT_REMIND_DAYS", "7"))


settings = Settings()
