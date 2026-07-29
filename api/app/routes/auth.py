from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import (
    create_access_token, create_refresh_token, decode_token, get_current_user,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request_body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Emails are stored lowercased; EmailStr also lowercases the domain part,
    # so normalise both sides before comparing.
    user = db.query(User).filter(User.email == request_body.email.lower()).first()
    if not user or not verify_password(request_body.password, user.password_hash):
        # Log the attempt without naming which half failed.
        log_event(db, "auth.login_failed", None, request, target_type="user",
                  target_id=request_body.email.lower())
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        log_event(db, "auth.login_denied_inactive", user, request)
        raise HTTPException(
            status_code=403,
            detail="This account is deactivated. Ask an admin to re-enable it.",
        )

    now = datetime.now(timezone.utc)
    user.last_login_at = now
    # Starts the 8-hour idle window enforced in app.auth.get_current_user.
    user.last_activity_at = now

    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    refresh_token = create_refresh_token(data={"sub": user.email})

    log_event(db, "auth.login", user, request, commit=False)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "totp_enrolled": user.totp_enabled,
        "role": user.role,
        "full_name": user.full_name,
    }


@router.post("/refresh", response_model=TokenResponse)
def refresh(request_body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(request_body.refresh_token)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is deactivated")

    # Refreshing counts as activity, so it also extends the idle window.
    user.last_activity_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "access_token": create_access_token(data={"sub": user.email, "role": user.role}),
        "refresh_token": create_refresh_token(data={"sub": user.email}),
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "totp_enrolled": user.totp_enabled,
        "role": user.role,
        "full_name": user.full_name,
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "must_change_password": current_user.must_change_password,
        "totp_enabled": current_user.totp_enabled,
        "assigned_verticals": current_user.assigned_verticals,
        "assigned_countries": current_user.assigned_countries,
        "last_login_at": current_user.last_login_at,
    }


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)):
    # JWTs are stateless, so clearing last_activity_at is what actually ends the
    # server-side session: the next request fails the idle check.
    current_user.last_activity_at = None
    log_event(db, "auth.logout", current_user, request, commit=False)
    db.commit()
    return {"message": "Logged out successfully"}
