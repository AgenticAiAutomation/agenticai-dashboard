"""Go-live gate.

Nothing reaches WordPress as a real publish until Jai writes
/var/www/agenticai-dashboard/SEO_LIVE_APPROVED.txt containing

    GO LIVE YYYY-MM-DD

with a date inside the last 24 hours. Until then every publish is forced to
WordPress status 'draft'. The check is re-read from disk on every call so
approval takes effect without a restart, and expires on its own.
"""
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from app.config import settings

_PATTERN = re.compile(r"GO\s+LIVE\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


@dataclass
class GoLiveStatus:
    approved: bool
    reason: str
    approval_date: Optional[date] = None

    @property
    def wp_status(self) -> str:
        """The WordPress post status this approval level permits."""
        return "publish" if self.approved else "draft"


def check_go_live(path: Optional[str] = None, now: Optional[datetime] = None) -> GoLiveStatus:
    approval_path = path or settings.SEO_LIVE_APPROVAL_FILE
    now = now or datetime.now()

    if not os.path.isfile(approval_path):
        return GoLiveStatus(
            approved=False,
            reason=(
                f"Go-live not approved: {approval_path} does not exist. "
                "Posts will be sent to WordPress as drafts."
            ),
        )

    try:
        with open(approval_path, "r", encoding="utf-8") as fh:
            contents = fh.read()
    except OSError as exc:
        return GoLiveStatus(approved=False, reason=f"Go-live file unreadable: {exc}")

    match = _PATTERN.search(contents)
    if not match:
        return GoLiveStatus(
            approved=False,
            reason=(
                "Go-live file present but malformed. Expected a line reading "
                "'GO LIVE YYYY-MM-DD'. Posts will be sent as drafts."
            ),
        )

    try:
        approval_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return GoLiveStatus(approved=False, reason="Go-live date is not a valid calendar date.")

    age = now.date() - approval_date
    if age > timedelta(days=1):
        return GoLiveStatus(
            approved=False,
            approval_date=approval_date,
            reason=(
                f"Go-live approval dated {approval_date.isoformat()} is older than 24 hours. "
                "Re-write SEO_LIVE_APPROVED.txt with today's date to publish live."
            ),
        )
    if approval_date > now.date():
        return GoLiveStatus(
            approved=False,
            approval_date=approval_date,
            reason=f"Go-live approval is dated in the future ({approval_date.isoformat()}).",
        )

    return GoLiveStatus(
        approved=True,
        approval_date=approval_date,
        reason=f"Go-live approved {approval_date.isoformat()}.",
    )
