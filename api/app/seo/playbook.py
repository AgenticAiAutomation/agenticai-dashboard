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


# --------------------------------------------------------------------------
# Playbook v2
# --------------------------------------------------------------------------
def v2_enabled_for(user: Any) -> bool:
    """v2 needs the Playbook for this login AND the BLOG_PLAYBOOK_V2 switch."""
    return bool(settings.BLOG_PLAYBOOK_V2) and enabled_for(user)


MUST_DO_MAX = 5


def clean_author_extras(raw: Any) -> Dict[str, Any]:
    """Coerce the writer's input to {best_pick: {option, reason}, notice, must_do}.

    Raises ValueError on anything over the limits, so the route can answer 422.
    """
    raw = raw if isinstance(raw, dict) else {}
    pick = raw.get("best_pick") if isinstance(raw.get("best_pick"), dict) else {}
    option = str(pick.get("option") or "").strip()
    reason = str(pick.get("reason") or "").strip()
    notice = str(raw.get("notice") or "").strip()
    must_do = [str(x).strip() for x in (raw.get("must_do") or []) if str(x).strip()]
    if len(must_do) > MUST_DO_MAX:
        raise ValueError(f"Must do takes at most {MUST_DO_MAX} points.")
    if any(len(v) > 2000 for v in [option, reason, notice, *must_do]):
        raise ValueError("An author field is longer than 2,000 characters.")
    return {
        "best_pick": {"option": option, "reason": reason} if option or reason else None,
        "notice": notice or None,
        "must_do": must_do or None,
    }


def load_author_extras(db: Session, article_id: UUID) -> Dict[str, Any]:
    """The three v2 author fields. Columns missing (migration 004 rolled back)
    reads as empty, so publishing never fails on them."""
    empty = {"best_pick": None, "notice": None, "must_do": None}
    try:
        with db.begin_nested():
            row = db.execute(
                text("SELECT author_best_pick, author_notice, author_must_do "
                     "FROM seo_articles WHERE id = :id"),
                {"id": str(article_id)},
            ).first()
    except Exception:
        return empty
    if row is None:
        return empty

    def decode(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    return {"best_pick": decode(row[0]), "notice": row[1], "must_do": decode(row[2])}


def save_author_extras(db: Session, article_id: UUID, extras: Dict[str, Any]) -> None:
    """Store cleaned extras (see clean_author_extras). The caller commits."""
    db.execute(
        text("UPDATE seo_articles SET author_best_pick = CAST(:pick AS JSONB), "
             "author_notice = :notice, author_must_do = CAST(:must AS JSONB) "
             "WHERE id = :id"),
        {"pick": json.dumps(extras["best_pick"]) if extras["best_pick"] else None,
         "notice": extras["notice"],
         "must": json.dumps(extras["must_do"]) if extras["must_do"] else None,
         "id": str(article_id)},
    )
