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
    # Who may use it: these emails, plus these dashboard roles.
    SUPERUSERS = _csv("FOLLOWUPS_SUPERUSERS",
                      os.environ.get("BACKLINK_OPS_SUPERUSERS",
                                     "contact@agenticaiautomation.co,jai.prajapati91@gmail.com"))
    ROLES      = _csv("FOLLOWUPS_ROLES", "owner,admin")
    USER_HOOK  = os.environ.get("FOLLOWUPS_USER_HOOK", "app.backlink_ops_hook:get_user_or_none")
    # The four follow-ups Jai listed on 22 Oct 2026 are loaded once into an
    # empty database. 0 = start empty.
    SEED       = _b("FOLLOWUPS_SEED", "1")
    VERSION    = "1.0.0"


settings = Settings()
