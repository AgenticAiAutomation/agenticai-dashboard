"""HTTP surface for the leads desk, under /api/wa-leads.

The whole desk is role-gated, not just the writes. It holds every enquirer's
phone number, email and what they said about their own business, so a signed-in
dashboard account is not on its own a reason to see it — WA_LEADS_READ_ROLES
decides, and it is `owner` by default.

Writing is gated again on top of that, and every write records who made it:
"who marked this rejected" has to be answerable.
"""
import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.models import User

from . import config, store
from .schemas import (
    Lead, LeadDetail, LeadPage, Meta, Notifications, Stats, StatusUpdate,
)

log = logging.getLogger("wa-leads")

router = APIRouter(prefix=config.API_PREFIX, tags=["wa-leads"])


def _actor(user: User) -> str:
    return getattr(user, "email", None) or f"user:{getattr(user, 'id', '?')}"


def _can_read(user: User) -> bool:
    return getattr(user, "role", None) in config.READ_ROLES


def _can_write(user: User) -> bool:
    return getattr(user, "role", None) in config.WRITE_ROLES


def require_read(current_user: User = Depends(get_current_user)) -> User:
    """Every route depends on this. 404 rather than 403 on purpose: to an
    account that may not see the desk, it should not be discoverable that a
    lead with a given id exists at all."""
    if not _can_read(current_user):
        raise HTTPException(status_code=404, detail="Not found.")
    return current_user


def require_write(current_user: User = Depends(require_read)) -> User:
    if not _can_write(current_user):
        raise HTTPException(
            status_code=403,
            detail="Your account can read the leads desk but not change a lead's status.",
        )
    return current_user


def require_db() -> None:
    """The funnel is a separate service on a separate deploy cycle. If its
    database is not there, say so plainly with a 503 rather than surfacing a
    sqlite error as a 500 — nothing is broken here."""
    if not store.available():
        raise HTTPException(
            status_code=503,
            detail=(
                "The funnel's leads database is not readable at "
                f"{store.db_path()}. The wa-funnel service may not be deployed yet."
            ),
        )


@router.get("/meta", response_model=Meta)
def meta(current_user: User = Depends(require_read)):
    """Everything the UI needs to draw its filters, in one call, and whether
    this user may change anything — so the page can hide controls it would
    only get a 403 from."""
    ok = store.available()
    return {
        "statuses": list(store.STATUSES),
        "open_statuses": list(store.OPEN_STATUSES),
        "industries": store.industries() if ok else [],
        "can_write": _can_write(current_user),
        "db_ok": ok,
    }


@router.get("/stats", response_model=Stats)
def get_stats(current_user: User = Depends(require_read), _=Depends(require_db)):
    return store.stats()


@router.get("/notifications", response_model=Notifications)
def notifications(
    since_id: int = Query(0, ge=0, description="Highest lead id this client has seen"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(require_read),
    _=Depends(require_db),
):
    """Polled by the dashboard's notification bell. Cheap on purpose: two
    counts and at most a handful of rows, so a 30-second poll costs nothing."""
    return store.notifications(since_id=since_id, limit=limit)


@router.get("", response_model=LeadPage)
def list_leads(
    status: Optional[str] = Query(None, description="A status, or 'open' for everything undecided"),
    qualified: Optional[bool] = Query(None),
    industry: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=120),
    days: Optional[int] = Query(None, ge=1, le=365),
    sort: str = Query("created_at"),
    direction: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(config.PAGE_SIZE_DEFAULT, ge=1, le=config.PAGE_SIZE_MAX),
    current_user: User = Depends(require_read),
    _=Depends(require_db),
):
    if status and status != "open" and status not in store.STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status: {status}")
    return store.list_leads(
        status=status, qualified=qualified, industry=industry, search=search,
        days=days, sort=sort, direction=direction, page=page, page_size=page_size,
    )


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, current_user: User = Depends(require_read), _=Depends(require_db)):
    lead = store.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="No lead with that id.")
    return lead


@router.patch("/{lead_id}/status", response_model=LeadDetail)
def update_status(
    lead_id: int,
    update: StatusUpdate,
    current_user: User = Depends(require_write),
    _=Depends(require_db),
):
    try:
        lead = store.set_status(lead_id, update.status, update.note, _actor(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.OperationalError as exc:
        # The commonest cause is the file being owned by the funnel's user and
        # not writable by this one. Say that, rather than "database is locked".
        log.error("wa-leads: cannot write %s: %s", store.db_path(), exc)
        raise HTTPException(
            status_code=503,
            detail="The leads database is readable but not writable by the dashboard.",
        ) from exc
    if not lead:
        raise HTTPException(status_code=404, detail="No lead with that id.")
    log.info("wa-leads: lead %s -> %s by %s", lead_id, update.status, _actor(current_user))
    return lead
