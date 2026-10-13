"""Daily Tracker + Idea Board — what each person did today, per website,
with proof, marks and review; plus a monthly idea board.

INSTALL (two lines in app/main.py, after Invoice Desk):

    from app.daily_tracker import register as register_daily_tracker
    register_daily_tracker(app)

Defensive like the other desks: both flags off, broken, or colliding with an
existing route → logs why, returns False, and the dashboard starts exactly as
before (/tasks/ then shows the old task list). Uninstall: delete the two lines
and restart. See docs/DAILY_TRACKER.md.
"""
import logging

from .config import settings

__version__ = settings.VERSION
_registered = False


def _log(app):
    for name in ("uvicorn.error", "gunicorn.error"):
        lg = logging.getLogger(name)
        if lg.handlers or (lg.parent and lg.parent.handlers):
            return lg
    return logging.getLogger("daily_tracker")


def register(app, logger=None):
    global _registered
    log = logger or _log(app)
    if not (settings.TRACKER or settings.IDEAS):
        log.info("[%s] disabled (FEATURE_DAILY_TRACKER and FEATURE_IDEA_BOARD off) — not mounted",
                 settings.LOG_PREFIX)
        return False
    if _registered:
        return True
    try:
        from . import routes, store
        try:
            from app.backlink_ops.adapters.fastapi_app import existing_paths
        except Exception:
            def existing_paths(a):
                return {getattr(r, "path", "") for r in getattr(a, "routes", [])}

        existing = existing_paths(app)
        for prefix in (settings.TASKS_PREFIX, settings.IDEAS_PREFIX):
            clash = sorted(p for p in existing if p == prefix or p.startswith(prefix + "/"))
            if clash:
                log.error("[%s] NOT mounted — %s already served by %s",
                          settings.LOG_PREFIX, prefix, clash[:3])
                return False
        store.init_db()
        routes.mount(app)
        _registered = True
        log.info("[%s] v%s mounted (tracker=%s ideas=%s) · db=%s", settings.LOG_PREFIX,
                 settings.VERSION, settings.TRACKER, settings.IDEAS, store.db_path())
        return True
    except Exception as exc:  # noqa: BLE001 — a feature must not break the host
        try:
            log.exception("[%s] failed to mount (%s) — dashboard continues without it",
                          settings.LOG_PREFIX, exc)
        except Exception:
            pass
        return False
