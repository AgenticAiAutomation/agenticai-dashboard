"""Invoice Desk — client-filled invoices with a review queue and PDF output.

INSTALL (two lines in app/main.py, after Backlink Ops):

    from app.invoice_desk import register as register_invoice_desk
    register_invoice_desk(app)

Defensive like Backlink Ops: disabled, broken, or colliding with an existing
route → logs why, returns False, and the dashboard starts exactly as before.
Uninstall: delete the two lines (or INVOICE_DESK_ENABLED=0) and restart.
See docs/INVOICE_DESK.md.
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
    return logging.getLogger("invoice_desk")


def register(app, logger=None):
    global _registered
    log = logger or _log(app)
    if not settings.ENABLED:
        log.info("[%s] disabled (INVOICE_DESK_ENABLED != 1) — not mounted", settings.LOG_PREFIX)
        return False
    if _registered:
        return True
    try:
        from fastapi import FastAPI  # noqa: F401 — this module is FastAPI-only
        from . import routes, store
        try:   # reuse the router-flattening walker; fall back if that module is gone
            from app.backlink_ops.adapters.fastapi_app import existing_paths
        except Exception:
            def existing_paths(a):
                return {getattr(r, "path", "") for r in getattr(a, "routes", [])}

        existing = existing_paths(app)
        for prefix in (settings.URL_PREFIX, settings.API_PREFIX):
            base = prefix.rstrip("/")
            clash = sorted(p for p in existing if p == base or p.startswith(base + "/"))
            if clash:
                log.error("[%s] NOT mounted — %s already served by %s",
                          settings.LOG_PREFIX, prefix, clash[:3])
                return False
        store.init_db()
        routes.mount(app)
        _registered = True
        log.info("[%s] v%s mounted at %s (api %s) · db=%s", settings.LOG_PREFIX,
                 settings.VERSION, settings.URL_PREFIX, settings.API_PREFIX, store.db_path())
        return True
    except Exception as exc:  # noqa: BLE001 — a feature must not break the host
        try:
            log.exception("[%s] failed to mount (%s) — dashboard continues without it",
                          settings.LOG_PREFIX, exc)
        except Exception:
            pass
        return False
