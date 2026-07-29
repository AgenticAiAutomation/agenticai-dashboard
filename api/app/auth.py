import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

ALGORITHM = "HS256"

# Password policy: min 12 chars, upper + lower + number + symbol.
PASSWORD_MIN_LENGTH = 12
_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>?/~`|"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def validate_password_policy(password: str) -> None:
    """Raise 400 with every rule the password fails, not just the first."""
    problems = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        problems.append("a number")
    if not any(c in _SYMBOLS for c in password):
        problems.append("a symbol")
    if problems:
        raise HTTPException(
            status_code=400,
            detail="Password must contain " + ", ".join(problems) + ".",
        )


def generate_password(length: int = 16) -> str:
    """Generate a password that satisfies the policy by construction."""
    alphabet = string.ascii_letters + string.digits + _SYMBOLS
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            validate_password_policy(candidate)
        except HTTPException:
            continue
        return candidate


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    now = datetime.now(timezone.utc)
    idle_limit = timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
    last_seen = user.last_activity_at

    # last_activity_at is the server-side session record: /auth/login sets it and
    # /auth/logout (and a password reset) clears it. A NULL therefore means "no
    # active session" — which is also the state of every account carried over
    # from before this column existed.
    if last_seen is None:
        raise HTTPException(
            status_code=401,
            detail="No active session. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    # Idle timeout is enforced server-side so a still-valid JWT cannot bypass it.
    if now - last_seen > idle_limit:
        raise HTTPException(
            status_code=401,
            detail="Session expired after 8 hours of inactivity. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Only write once a minute — this runs on every authenticated request.
    if now - last_seen < timedelta(seconds=60):
        return user

    user.last_activity_at = now
    try:
        db.commit()
    except Exception:
        db.rollback()
    return user


def require_role(allowed_roles: list):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker
