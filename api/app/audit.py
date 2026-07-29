"""Audit trail helper.

Every call writes one immutable row to audit_events. Logging must never break
the request that triggered it, so failures are swallowed after a rollback of
the audit insert only.
"""
from typing import Optional
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    # nginx sets X-Forwarded-For; take the original client, not the proxy chain.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def log_event(
    db: Session,
    action: str,
    user: Optional[User] = None,
    request: Optional[Request] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    detail: Optional[str] = None,
    commit: bool = True,
) -> None:
    """Record an action. `commit=False` when the caller owns the transaction."""
    event = AuditEvent(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(event)
    if commit:
        try:
            db.commit()
        except Exception:
            db.rollback()
