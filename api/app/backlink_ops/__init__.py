"""Backlink Ops — a self-contained feature module for the AgenticAI SEO dashboard.

INSTALLATION IS ONE LINE, and it is the same line on either framework:

    from app.backlink_ops import register as register_backlink_ops
    register_backlink_ops(app)          # FastAPI() or Flask() — it detects which

That call is defensive by design. If this module is disabled, broken, on the
wrong framework, or its database is unreachable, `register` logs the reason and
returns False — the host application starts and serves every pre-existing route
exactly as before. A feature must never be able to take the dashboard down.

Uninstall: delete the two lines, restart. See docs/BCP_AND_ROLLBACK.md.
"""
import logging

from .config import settings

__version__ = settings.VERSION
_registered = False


def _resolve_logger(app, explicit):
    """Find a logger whose lines will actually be seen.

    `logging.getLogger("backlink_ops")` is a trap: on a FastAPI host nothing
    configures that name, so every line this module writes — including the
    mount confirmation — is silently dropped. Flask hosts have `app.logger`;
    ASGI hosts have an already-configured server logger. Use whichever exists.
    Never adds a handler, changes a level, or touches logging config.
    """
    if explicit is not None:
        return explicit
    flask_logger = getattr(app, "logger", None)
    if flask_logger is not None:
        return flask_logger
    for name in ("uvicorn.error", "gunicorn.error", "hypercorn.error", "uvicorn", "app"):
        candidate = logging.getLogger(name)
        if candidate.handlers or (candidate.parent and candidate.parent.handlers):
            return candidate
    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger("backlink_ops")   # propagates to the configured root
    # Nothing is configured at all (a bare script or a test). Make sure the
    # module is not silent: one stream handler on our OWN logger only.
    fallback = logging.getLogger("backlink_ops")
    if not fallback.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        fallback.addHandler(h)
        fallback.setLevel(logging.INFO)
    return fallback


def _detect(app):
    """Returns ('fastapi'|'flask', adapter_module) or (None, None)."""
    mod = type(app).__module__ or ""
    name = type(app).__name__
    if name == "FastAPI" or mod.startswith("fastapi"):
        from .adapters import fastapi_app
        return "fastapi", fastapi_app
    if name == "Flask" or mod.startswith("flask"):
        from .adapters import flask_app
        return "flask", flask_app
    # Duck-typing fallback, in case of a subclass.
    if hasattr(app, "include_router"):
        from .adapters import fastapi_app
        return "fastapi", fastapi_app
    if hasattr(app, "register_blueprint"):
        from .adapters import flask_app
        return "flask", flask_app
    return None, None


def register(app, logger=None):
    """Mount the feature. Returns True if mounted, False if skipped.

    Never raises. Never modifies existing config, routes, templates, database
    connections, logging handlers or extensions belonging to the host.
    """
    global _registered
    log = _resolve_logger(app, logger)

    if not settings.ENABLED:
        log.info("[%s] disabled (BACKLINK_OPS_ENABLED != 1) — not mounted",
                 settings.LOG_PREFIX)
        return False
    if _registered:
        log.info("[%s] already mounted — skipping", settings.LOG_PREFIX)
        return True

    try:
        framework, adapter = _detect(app)
        if not adapter:
            log.error("[%s] NOT mounted — unrecognised application object %r. "
                      "Supported: FastAPI, Flask.", settings.LOG_PREFIX, type(app))
            return False

        from . import audit, store
        audit.set_logger(log)

        # Collision guard: refuse to mount rather than shadow an existing route.
        # Compares full path segments, so an existing /api/seo/backlinks does
        # NOT look like a clash with /api/seo/backlink-ops.
        existing = adapter.existing_paths(app)
        for prefix in (settings.URL_PREFIX, settings.API_PREFIX):
            base = prefix.rstrip("/")
            clash = sorted(p for p in existing if p == base or p.startswith(base + "/"))
            if clash:
                log.error("[%s] NOT mounted — %s is already served by %s. "
                          "Change BACKLINK_OPS_URL_PREFIX / BACKLINK_OPS_API_PREFIX.",
                          settings.LOG_PREFIX, prefix, clash[:3])
                return False

        store.init_db(log)
        adapter.mount(app, log)

        _registered = True
        log.info("[%s] v%s mounted on %s at %s (api %s) · db=%s · ai=%s",
                 settings.LOG_PREFIX, settings.VERSION, framework,
                 settings.URL_PREFIX, settings.API_PREFIX, store.db_path(),
                 settings.AI_PROVIDER if settings.AI_KEY else "rules-only")
        return True

    except Exception as exc:  # noqa: BLE001 — a feature must not break the host
        try:
            log.exception("[%s] failed to mount (%s) — the dashboard continues "
                          "without it", settings.LOG_PREFIX, exc)
        except Exception:
            pass
        return False
