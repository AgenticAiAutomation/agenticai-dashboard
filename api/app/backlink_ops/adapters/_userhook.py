"""Finding the user the host application already authenticated.

Shared by both adapters. Tried in order; the first that yields something wins:

  1. BACKLINK_OPS_USER_HOOK — "module:callable" you point at your own
     dependency. Always correct, always preferred. It receives the framework's
     request object and returns anything dict-like with email/name/role(s), or
     None. Set this and the rest is dead code.
  2. request.state.user / request.scope["user"] (FastAPI & Starlette middleware)
  3. flask.g.user / flask.session (Flask)
  4. A JWT in the Authorization header or a cookie, verified with
     BACKLINK_OPS_JWT_SECRET (or JWT_SECRET_KEY / SECRET_KEY). Uses whichever
     JWT library the host already has — PyJWT or python-jose. If neither is
     installed this adapter is skipped; nothing new is imported.
  5. Anonymous, only when BACKLINK_OPS_ALLOW_ANON=1 (dev and first boot).

An UNVERIFIED token is never trusted: with no secret configured, step 4 is
skipped entirely rather than decoding without a signature check.
"""
import importlib

from ..config import settings

_HOOK = None
_HOOK_LOADED = False


def load_hook():
    global _HOOK, _HOOK_LOADED
    if _HOOK_LOADED:
        return _HOOK
    _HOOK_LOADED = True
    spec = (settings.USER_HOOK or "").strip()
    if spec and ":" in spec:
        mod, _, attr = spec.partition(":")
        try:
            _HOOK = getattr(importlib.import_module(mod), attr)
        except Exception:
            _HOOK = None
    return _HOOK


def as_dict(obj):
    """Accepts a dict, a pydantic model, an ORM row or a plain object."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        d = obj
    elif hasattr(obj, "model_dump"):
        try:
            d = obj.model_dump()
        except Exception:
            d = {}
    elif hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            d = obj.dict()
        except Exception:
            d = {}
    else:
        d = {k: getattr(obj, k, None)
             for k in ("id", "name", "username", "full_name", "email", "role", "roles")}
    email = d.get("email") or ""
    name = d.get("name") or d.get("username") or d.get("full_name") or ""
    if not (email or name or d.get("id")):
        return None
    return d


def _jwt_decode(token):
    secret = settings.JWT_SECRET
    if not secret or not token:
        return None
    algs = settings.JWT_ALGS or ["HS256"]
    try:
        import jwt as pyjwt  # PyJWT
        return pyjwt.decode(token, secret, algorithms=algs)
    except ImportError:
        pass
    except Exception:
        return None
    try:
        from jose import jwt as jose_jwt  # python-jose
        return jose_jwt.decode(token, secret, algorithms=algs)
    except ImportError:
        return None
    except Exception:
        return None


def from_token(auth_header, cookies):
    token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token and cookies:
        for name in settings.JWT_COOKIES:
            v = cookies.get(name)
            if v:
                token = v[7:].strip() if v.lower().startswith("bearer ") else v
                break
    claims = _jwt_decode(token)
    if not claims:
        return None
    return {"id": claims.get("sub") or claims.get("user_id") or claims.get("id"),
            "email": claims.get("email") or (claims.get("sub") if "@" in
                     str(claims.get("sub") or "") else ""),
            "name": claims.get("name") or claims.get("username") or claims.get("email"),
            "role": claims.get("role"), "roles": claims.get("roles")}


def anonymous():
    if not settings.ALLOW_ANON:
        return None
    return {"id": "anon", "name": "Desk user", "email": "", "role": "admin"}
