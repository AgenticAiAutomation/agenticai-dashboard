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
from typing import Any, Dict, Optional
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


def enabled_for(user: Any) -> bool:
    """True when the Playbook writer is switched on for this login."""
    if settings.BLOG_PLAYBOOK_ENABLED:
        return True
    email = (getattr(user, "email", None) or "").strip().lower()
    return bool(email) and email in _allowed_emails()


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
