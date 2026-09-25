"""WhatsApp leads desk — the CRM view over wa-funnel's leads.

INSTALLATION IS ONE LINE:

    from app.wa_leads import register as register_wa_leads
    register_wa_leads(app)

Defensive by the same rule backlink_ops follows: if this module is disabled,
broken, or the funnel's database is missing, `register` logs why and returns
False. The dashboard starts and serves every pre-existing route exactly as
before. A feature must never be able to take the dashboard down — and this one
depends on a file owned by a *different service*, so that is not theoretical.

Uninstall: delete the two lines, restart.
"""
import logging

from . import config

__version__ = config.VERSION
_registered = False


def _resolve_logger(app, explicit):
    """Find a logger whose lines will actually be seen. `logging.getLogger`
    on our own name is a trap on a FastAPI host: nothing configures it, so
    every line is dropped, including the mount confirmation."""
    if explicit is not None:
        return explicit
    for name in ("uvicorn.error", "gunicorn.error", "uvicorn", "app"):
        candidate = logging.getLogger(name)
        if candidate.handlers or (candidate.parent and candidate.parent.handlers):
            return candidate
    return logging.getLogger("wa_leads")


def register(app, logger=None) -> bool:
    """Mount the desk. Returns True if mounted, False if skipped. Never raises."""
    global _registered
    log = _resolve_logger(app, logger)

    if not config.ENABLED:
        log.info("[%s] disabled (WA_LEADS_ENABLED != 1) — not mounted", config.LOG_PREFIX)
        return False
    if _registered:
        log.info("[%s] already mounted — skipping", config.LOG_PREFIX)
        return True

    try:
        from . import routes, store

        # Refuse to shadow an existing route rather than quietly winning.
        base = config.API_PREFIX.rstrip("/")
        existing = {getattr(r, "path", "") for r in app.routes}
        clash = sorted(p for p in existing if p == base or p.startswith(base + "/"))
        if clash:
            log.error("[%s] NOT mounted — %s is already served by %s",
                      config.LOG_PREFIX, config.API_PREFIX, clash[:3])
            return False

        app.include_router(routes.router)
        _registered = True

        # Mount even when the database is missing. The funnel deploys on its
        # own cycle, and the endpoints answer 503 with an explanation until it
        # is there — which is more useful than a route that does not exist.
        log.info("[%s] v%s mounted at %s · db=%s (%s) · write roles=%s",
                 config.LOG_PREFIX, config.VERSION, config.API_PREFIX,
                 store.db_path(),
                 "readable" if store.available() else "NOT READABLE YET",
                 ",".join(config.WRITE_ROLES))
        return True

    except Exception as exc:  # noqa: BLE001 — a feature must not break the host
        try:
            log.exception("[%s] failed to mount (%s) — the dashboard continues "
                          "without it", config.LOG_PREFIX, exc)
        except Exception:
            pass
        return False
