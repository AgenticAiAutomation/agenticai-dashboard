"""Blog Playbook — feature flag and block storage.

The Playbook writer is a second way of producing the same Markdown body the
dashboard already stores. Its only state of its own is `playbook_blocks`, the
writer's structured form, kept so the builder can reopen an article filled in.

That column is read and written here with plain SQL and is deliberately NOT
mapped on SeoArticle. With the flag off nothing in the application ever
mentions it, so the API keeps working even if the migration has not been run
or has been rolled back — the rollback plan depends on that.

Nothing in this module is consulted by scoring, Rank Math, the publish gate
or the publisher's JSON contract.
"""
import json
import os
import tempfile
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

# A builder document is a few KB. Anything far larger is not a writer's work,
# so it is refused rather than stored.
MAX_BLOCKS_BYTES = 200_000


def _allowed_emails() -> set:
    return {e.strip().lower() for e in (settings.BLOG_PLAYBOOK_USERS or "").split(",")
            if e.strip()}


# --------------------------------------------------------------------------
# Access granted from the dashboard
#
# Admins tick who gets the Playbook on the Users page. That list lives in a
# small JSON file the API owns (api/instance/, like the other desks' data), so
# granting access needs no server command, no restart and no migration. It
# only ever ADDS people on top of the server settings above; the server-side
# "off" (ops/blog-playbook-flag.sh off) moves the file aside as well.
# --------------------------------------------------------------------------
_access_cache: Dict[str, Any] = {"mtime": None, "value": None}


def _empty_access() -> Dict[str, Any]:
    return {"everyone": False, "emails": []}


def load_access() -> Dict[str, Any]:
    """The dashboard-granted access list. Any problem reading it = nobody."""
    path = settings.BLOG_PLAYBOOK_ACCESS_FILE
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return _empty_access()
    if _access_cache["mtime"] == mtime and _access_cache["value"] is not None:
        return _access_cache["value"]
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        value = {
            "everyone": raw.get("everyone") is True,
            "emails": sorted({str(e).strip().lower() for e in raw.get("emails") or []
                              if str(e).strip()}),
        }
    except (OSError, ValueError, AttributeError):
        return _empty_access()
    _access_cache.update(mtime=mtime, value=value)
    return value


def save_access(everyone: bool, emails: List[str]) -> Dict[str, Any]:
    """Write the list atomically, so a reader never sees half a file."""
    value = {"everyone": bool(everyone),
             "emails": sorted({e.strip().lower() for e in emails if e.strip()})}
    path = settings.BLOG_PLAYBOOK_ACCESS_FILE
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".playbook-access-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=1)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    _access_cache.update(mtime=None, value=None)
    return value


def enabled_for(user: Any) -> bool:
    """True when the Playbook writer is switched on for this login."""
    if settings.BLOG_PLAYBOOK_ENABLED:
        return True
    email = (getattr(user, "email", None) or "").strip().lower()
    if not email:
        return False
    if email in _allowed_emails():
        return True
    access = load_access()
    return access["everyone"] or email in access["emails"]


def load_blocks(db: Session, article_id: UUID) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text("SELECT playbook_blocks FROM seo_articles WHERE id = :id"),
        {"id": str(article_id)},
    ).first()
    if row is None or row[0] is None:
        return None
    value = row[0]
    # psycopg2 decodes JSONB to Python already; a text driver would not.
    return json.loads(value) if isinstance(value, str) else value


def save_blocks(db: Session, article_id: UUID, blocks: Dict[str, Any]) -> None:
    """Store the builder document as-is. The caller commits."""
    encoded = json.dumps(blocks, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_BLOCKS_BYTES:
        raise ValueError(f"playbook_blocks is larger than {MAX_BLOCKS_BYTES} bytes")
    db.execute(
        text("UPDATE seo_articles SET playbook_blocks = CAST(:blocks AS JSONB) "
             "WHERE id = :id"),
        {"blocks": encoded, "id": str(article_id)},
    )
