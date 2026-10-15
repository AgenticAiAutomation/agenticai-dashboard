"""Daily Tracker + Idea Board — configuration.

Same contract as Backlink Ops and Invoice Desk: every switch is an environment
variable. Both flags default OFF; with both off nothing is mounted and /tasks/
shows the old task list exactly as before.
"""
import os


def _b(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _csv(name, default=""):
    return [x.strip().lower() for x in os.environ.get(name, default).split(",") if x.strip()]


class Settings:
    TRACKER     = _b("FEATURE_DAILY_TRACKER", "0")
    IDEAS       = _b("FEATURE_IDEA_BOARD", "0")
    # T7: tasks (SMART), targets, Red/Amber/Green, Mirror, points and tiers.
    TASKS       = _b("FEATURE_TASK_MANAGER", "0")
    # Working weekdays for target splits, Monday = 0. Default Monday-Saturday.
    WORKDAYS    = [int(x) for x in os.environ.get("TASK_MANAGER_WORKDAYS", "0,1,2,3,4,5").split(",") if x.strip()]
    READ_ONLY   = _b("DAILY_TRACKER_READ_ONLY", "0")     # BCP degrade: serve, refuse writes

    # Spec'd paths. They do not collide with the old /tasks router (no /api).
    TASKS_PREFIX = "/api/tasks"
    IDEAS_PREFIX = "/api/ideas"

    # Its OWN sqlite file; the dashboard's Postgres is never touched.
    DB_PATH     = os.environ.get("DAILY_TRACKER_DB", "instance/daily_tracker.db")
    BACKUP_DIR  = os.environ.get("DAILY_TRACKER_BACKUP_DIR", "backups/daily_tracker")

    # Reviewers: these emails, plus dashboard roles owner/admin.
    SUPERUSERS  = _csv("DAILY_TRACKER_SUPERUSERS",
                       os.environ.get("BACKLINK_OPS_SUPERUSERS",
                                      "contact@agenticaiautomation.co,jai.prajapati91@gmail.com"))
    ADMIN_ROLES = _csv("DAILY_TRACKER_ADMIN_ROLES", "owner,admin")
    # Same non-raising identity wrapper Invoice Desk uses.
    USER_HOOK   = os.environ.get("DAILY_TRACKER_USER_HOOK",
                                 "app.backlink_ops_hook:get_user_or_none")

    LOG_PREFIX  = "daily-tracker"
    VERSION     = "1.1.0"
    SCHEMA_VERSION = 2


settings = Settings()
