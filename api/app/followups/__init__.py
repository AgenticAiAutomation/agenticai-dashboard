"""Follow-ups — the CRM's "who do I call, when, about what" list.

Contacts (from the WhatsApp leads or typed in) and follow-up actions with a
date, priority and purpose. Marking one done records what happened (the log
the next call starts from) and can schedule the next step in one go.

INSTALL (two lines in app/main.py):
    from app.followups import register as register_followups
    register_followups(app)
Off unless FEATURE_FOLLOWUPS=1. Own SQLite file; never raises. See docs/FOLLOWUPS.md.
"""
import logging

from .config import settings

_registered = False


def register(app, logger=None):
    global _registered
    log = logger or logging.getLogger("uvicorn.error")
    if not settings.ENABLED:
        log.info("[followups] disabled (FEATURE_FOLLOWUPS != 1) — not mounted")
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
        p = settings.API_PREFIX
        clash = sorted(x for x in existing_paths(app) if x == p or x.startswith(p + "/"))
        if clash:
            log.error("[followups] NOT mounted — %s already served by %s", p, clash[:3])
            return False
        store.init_db()
        routes.mount(app)
        _registered = True
        log.info("[followups] v%s mounted at %s · db=%s", settings.VERSION, p, store.db_path())
        return True
    except Exception as exc:  # noqa: BLE001 — a feature must not break the host
        try:
            log.exception("[followups] failed to mount (%s) — dashboard continues without it", exc)
        except Exception:
            pass
        return False
