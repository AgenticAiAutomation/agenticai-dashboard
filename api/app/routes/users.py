"""User management. Admin-only, fully audited.

Roles:
  admin     — Jai. Full access, including user management and publishing.
  seo_lead  — the SEO team. Create/edit articles; no user management, no billing.
  viewer    — read-only, reserved for future use.

'owner', 'seo', and 'writer' are the pre-SEO-module roles. They still
authenticate and map onto the same permission sets so existing accounts keep
working; new accounts should use the three roles above.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import (
    generate_password, get_password_hash, require_role, validate_password_policy,
)
from app.database import get_db
from app.models import ALL_ROLES, ROLE_ADMIN, AuditEvent, User
from app.seo import enums
from app.seo.models import SeoArticle

router = APIRouter(prefix="/users", tags=["users"])

ASSIGNABLE_ROLES = ["admin", "seo_lead", "viewer"]
VALID_VERTICALS = {e.value for e in enums.Vertical}
VALID_COUNTRIES = {e.value for e in enums.Country}


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1)
    role: str
    # Omit to have a compliant 16-character password generated and returned once.
    password: Optional[str] = None
    assigned_verticals: Optional[List[str]] = None
    assigned_countries: Optional[List[str]] = None
    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    assigned_verticals: Optional[List[str]] = None
    assigned_countries: Optional[List[str]] = None


class PasswordResetRequest(BaseModel):
    # Omit to generate one.
    password: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool
    totp_enabled: bool
    assigned_verticals: Optional[List[str]] = None
    assigned_countries: Optional[List[str]] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithStats(UserResponse):
    articles_drafted_this_week: int = 0
    avg_score: Optional[float] = None


class CreatedUserResponse(UserResponse):
    # Shown exactly once, at creation. Never retrievable afterwards.
    generated_password: Optional[str] = None
    delivery_note: str


class AuditEventResponse(BaseModel):
    id: int
    user_email: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    detail: Optional[str]
    ip: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------
def _validate_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role}'. Assignable roles: "
                   f"{', '.join(ASSIGNABLE_ROLES)}.",
        )


def _validate_scopes(verticals: Optional[List[str]],
                     countries: Optional[List[str]]) -> None:
    bad_verticals = set(verticals or []) - VALID_VERTICALS
    if bad_verticals:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown vertical(s): {', '.join(sorted(bad_verticals))}. "
                   f"Valid: {', '.join(sorted(VALID_VERTICALS))}.")
    bad_countries = set(countries or []) - VALID_COUNTRIES
    if bad_countries:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown country/countries: {', '.join(sorted(bad_countries))}. "
                   f"Valid: {', '.join(sorted(VALID_COUNTRIES))}.")


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.get("", response_model=List[UserWithStats])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
    include_inactive: bool = True,
):
    query = db.query(User)
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    users = query.order_by(User.full_name).all()

    week_start = datetime.now(timezone.utc).date()
    week_start = week_start.fromordinal(week_start.toordinal() - week_start.weekday())

    results = []
    for user in users:
        drafted = (db.query(func.count(SeoArticle.id))
                   .filter(SeoArticle.assigned_to == user.id,
                           SeoArticle.created_at >= week_start).scalar()) or 0
        avg_score = (db.query(func.avg(SeoArticle.current_score))
                     .filter(SeoArticle.assigned_to == user.id,
                             SeoArticle.current_score.isnot(None)).scalar())
        payload = UserWithStats.model_validate(user, from_attributes=True)
        payload.articles_drafted_this_week = int(drafted)
        payload.avg_score = round(float(avg_score), 1) if avg_score is not None else None
        results.append(payload)
    return results


@router.post("", response_model=CreatedUserResponse, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    _validate_role(payload.role)
    _validate_scopes(payload.assigned_verticals, payload.assigned_countries)

    generated = None
    if payload.password:
        validate_password_policy(payload.password)
        password = payload.password
    else:
        password = generate_password(16)
        generated = password

    user = User(
        email=email,
        password_hash=get_password_hash(password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
        must_change_password=payload.must_change_password,
        assigned_verticals=payload.assigned_verticals,
        assigned_countries=payload.assigned_countries,
    )
    db.add(user)
    log_event(db, "user.created", current_user, request, target_type="user",
              target_id=email, detail=f"role={payload.role}", commit=False)
    db.commit()
    db.refresh(user)

    # Build the response in one pass. Validating the ORM object straight into
    # CreatedUserResponse raises before the next two lines can run, because
    # `delivery_note` is required and a User has no such attribute — and the
    # commit above has already happened, so the caller saw a 500 for a user
    # that was created successfully.
    delivery_note = (
        "This password is shown once and is not recoverable. Send it to the user "
        "over a channel they already control, and have them change it on first login."
        if generated else
        "Password was supplied by the admin; nothing is returned."
    )
    return CreatedUserResponse(
        **UserResponse.model_validate(user, from_attributes=True).model_dump(),
        generated_password=generated,
        delivery_note=delivery_note,
    )


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = []
    if payload.full_name is not None:
        user.full_name = payload.full_name
        changes.append("full_name")
    if payload.role is not None:
        _validate_role(payload.role)
        if user.id == current_user.id and payload.role not in ROLE_ADMIN:
            raise HTTPException(
                status_code=400,
                detail="You cannot remove your own admin role — that would lock you "
                       "out of user management.")
        user.role = payload.role
        changes.append(f"role={payload.role}")
    if payload.is_active is not None:
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(status_code=400,
                                detail="You cannot deactivate your own account.")
        user.is_active = payload.is_active
        changes.append(f"is_active={payload.is_active}")
    if payload.assigned_verticals is not None or payload.assigned_countries is not None:
        _validate_scopes(payload.assigned_verticals, payload.assigned_countries)
        if payload.assigned_verticals is not None:
            user.assigned_verticals = payload.assigned_verticals
            changes.append("assigned_verticals")
        if payload.assigned_countries is not None:
            user.assigned_countries = payload.assigned_countries
            changes.append("assigned_countries")

    log_event(db, "user.updated", current_user, request, target_type="user",
              target_id=user.email, detail=", ".join(changes) or "no changes",
              commit=False)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    generated = None
    if payload.password:
        validate_password_policy(payload.password)
        password = payload.password
    else:
        password = generate_password(16)
        generated = password

    user.password_hash = get_password_hash(password)
    user.must_change_password = True
    # Force the next request to re-authenticate rather than ride the old session.
    user.last_activity_at = None

    log_event(db, "user.password_reset", current_user, request, target_type="user",
              target_id=user.email, commit=False)
    db.commit()
    return {
        "email": user.email,
        "generated_password": generated,
        "must_change_password": True,
        "note": "Shown once. The user's active sessions have been invalidated.",
    }


@router.post("/me/change-password")
def change_own_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(list(ALL_ROLES))),
):
    from app.auth import verify_password

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    validate_password_policy(payload.new_password)
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400,
                            detail="The new password must differ from the current one.")

    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    log_event(db, "user.password_changed", current_user, request, target_type="user",
              target_id=current_user.email, commit=False)
    db.commit()
    return {"message": "Password updated"}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    email = user.email
    db.delete(user)
    log_event(db, "user.deleted", current_user, request, target_type="user",
              target_id=email, commit=False)
    db.commit()
    return {"message": f"Deleted {email}"}


@router.get("/audit-log", response_model=List[AuditEventResponse])
def audit_log(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
    limit: int = 200,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
):
    query = db.query(AuditEvent)
    if action:
        query = query.filter(AuditEvent.action == action)
    if user_id is not None:
        query = query.filter(AuditEvent.user_id == user_id)
    return query.order_by(AuditEvent.created_at.desc()).limit(min(limit, 1000)).all()
