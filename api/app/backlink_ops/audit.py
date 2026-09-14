"""Backlink Ops — log stamping and audit trail. Framework-free.

Two destinations, on purpose:

  * the HOST APPLICATION'S OWN LOGGER, handed to us once at registration, so
    every action lands in whatever log file the dashboard already writes, with
    a fixed `[backlink-ops]` prefix. No new handler, no new file, no level
    change. `grep backlink-ops` isolates this feature; every other line in that
    file is untouched.

  * `bo_audit` — a queryable trail with actor, role, action and detail, so
    "who approved this link and when" survives log rotation.

Rule for contributors: every state change goes through stamp(). A silent write
is a bug.
"""
import json
import logging

from .config import settings
from . import store

_logger = logging.getLogger("backlink_ops")


def set_logger(logger):
    """Called once by register(). Everything after this lands in the host's log."""
    global _logger
    if logger is not None:
        _logger = logger


def stamp(action, actor="system", role="system", target=None, detail=None, level="info"):
    line = f"[{settings.LOG_PREFIX}] {action} actor={actor} role={role}"
    if target:
        line += f" target={target}"
    if detail:
        try:
            line += f" detail={json.dumps(detail, separators=(',', ':'), default=str)[:600]}"
        except Exception:
            line += f" detail={str(detail)[:600]}"
    try:
        getattr(_logger, level, _logger.info)(line)
    except Exception:
        pass
    try:
        conn = store.connect()
        with conn:
            conn.execute(
                "INSERT INTO bo_audit(at, actor, role, action, target, detail) VALUES (?,?,?,?,?,?)",
                (store.now_iso(), actor, role, action, target,
                 json.dumps(detail, default=str)[:4000] if detail else None))
    except Exception:
        # Auditing must never break the request it is describing.
        pass


def stamp_user(user, action, target=None, detail=None):
    u = user or {}
    stamp(action, actor=u.get("name", "unknown"), role=u.get("role", "unknown"),
          target=target, detail=detail)


def recent(limit=200):
    rows = store.connect().execute(
        "SELECT * FROM bo_audit ORDER BY id DESC LIMIT ?", (int(limit),))
    return [dict(r) for r in rows]
