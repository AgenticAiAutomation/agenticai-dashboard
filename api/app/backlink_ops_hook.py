"""Non-raising identity lookup for the Backlink Ops desk.

New file — nothing in the existing application imports it, and it does not
modify app.auth or app.database. It exists only to satisfy the shape the
Backlink Ops module's user hook expects: a synchronous callable taking a
request and returning a user (or None), never raising.

Why this can't just be `get_current_user` directly, wrapped in try/except
(the pattern docs/RUNBOOK.md and WORKORDER.md Step 3 sketch as the default):

  1. get_current_user is a FastAPI dependency — its real signature is
     `(credentials: HTTPAuthorizationCredentials = Depends(security),
       db: Session = Depends(get_db))`. It cannot be called with a bare
     Request; the credentials and db session have to be constructed here.
  2. Backlink Ops calls its hook synchronously and unawaited
     (`raw = hook(request)` in adapters/fastapi_app.py). get_current_user
     itself is sync, but FastAPI's own HTTPBearer.__call__ (the usual way to
     get an HTTPAuthorizationCredentials) is async — using it here would hand
     back an un-awaited coroutine, which the module's own generic dict-ifier
     silently turns into "no identity", i.e. everyone reads as logged out.
     So the Authorization header is parsed by hand instead.

Everything else — token decode, idle-timeout, is_active, the
last_activity_at touch that keeps a session alive — is get_current_user's
existing logic, reused as-is, not reimplemented.

  3. The result is copied into a plain dict BEFORE the session closes.
     get_current_user commits (the once-a-minute last_activity_at bump), and
     SessionLocal keeps SQLAlchemy's default expire_on_commit=True, so after
     that commit every attribute on the User row is expired. Hand the row
     itself back, close the session, and the desk's first `user.email` raises
     DetachedInstanceError. It only works inside the first minute after login
     — which is exactly why a quick rehearsal never shows it.
"""
from fastapi.security import HTTPAuthorizationCredentials

from .auth import get_current_user
from .database import SessionLocal


def get_user_or_none(request):
    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = SessionLocal()
    try:
        user = get_current_user(credentials=credentials, db=db)
        # Read while still attached: a detached, expired row cannot be read.
        return {
            "id": user.id,
            "email": user.email,
            "name": user.full_name,
            "role": user.role,
        }
    except Exception:
        # Expired / invalid / deactivated / not found — the desk treats all
        # of these as "no identity" rather than surfacing the dashboard's
        # own 401/403, which would be the wrong error shape here anyway.
        return None
    finally:
        db.close()
