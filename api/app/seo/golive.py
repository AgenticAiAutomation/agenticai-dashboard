"""Go-live gate — off by default.

This was a launch safeguard. Every publish was forced to 'draft' until an owner
wrote SEO_LIVE_APPROVED.txt containing 'GO LIVE YYYY-MM-DD' dated within 24
hours, and the approval expired daily. A draft article is excluded from the blog
index and the sitemap and is never sent to IndexNow, so a lapsed approval meant
articles the team believed were published were invisible to readers and Google.

That trade made sense before launch and stopped making sense after it. With
settings.SEO_REQUIRE_GOLIVE_APPROVAL False — the default — pressing Publish in
the dashboard is the approval, and the article is listed, sitemapped and
submitted to IndexNow in one step.

Set that flag True to restore the manual gate; everything below still works, is
re-read from disk on every call so approval takes effect without a restart, and
expires on its own.
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
        """The publish status this approval level permits."""
        return "publish" if self.approved else "draft"


def check_go_live(path: Optional[str] = None, now: Optional[datetime] = None) -> GoLiveStatus:
    # Publishing is self-approving unless the manual gate is switched back on.
    # Passing an explicit path means a caller is testing the gate itself, so the
    # file is still honoured there regardless of the setting.
    if path is None and not settings.SEO_REQUIRE_GOLIVE_APPROVAL:
        return GoLiveStatus(
            approved=True,
            approval_date=(now or datetime.now()).date(),
            reason="Publishing from the dashboard is the approval.",
        )

    approval_path = path or settings.SEO_LIVE_APPROVAL_FILE
    now = now or datetime.now()

    if not os.path.isfile(approval_path):
        return GoLiveStatus(
            approved=False,
            reason=(
                f"Go-live not approved: {approval_path} does not exist. "
                "Articles will be written as drafts."
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
                "'GO LIVE YYYY-MM-DD'. Articles will be written as drafts."
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
