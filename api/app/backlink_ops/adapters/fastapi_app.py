"""FastAPI adapter — the one used by agenticai-dashboard.

Builds an APIRouter for the JSON API and a second one for the page. Both are
mounted by `register()`; neither touches an existing route.
"""
import hmac

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .. import service
from ..config import settings
from ..identity import normalise
from . import _userhook as uh


def current_user(request: Request):
    hook = uh.load_hook()
    if hook:
        try:
            raw = hook(request)
        except Exception:
            raw = None
        u = normalise(uh.as_dict(raw))
        if u:
            return u

    for getter in (lambda: getattr(request.state, "user", None),
                   lambda: request.scope.get("user")):
        try:
            raw = getter()
        except Exception:
            raw = None
        # Starlette's UnauthenticatedUser has is_authenticated False
        if raw is not None and getattr(raw, "is_authenticated", True):
            u = normalise(uh.as_dict(raw))
            if u:
                return u

    u = normalise(uh.from_token(request.headers.get("authorization"),
                                request.cookies))
    if u:
        return u
    return normalise(uh.anonymous())


def _same(a, b):
    return hmac.compare_digest(str(a).encode(), str(b).encode())


def _json(result):
    status, payload = result
    return JSONResponse(payload, status_code=status)


def build_routers():
    api = APIRouter(tags=["backlink-ops"])
    page = APIRouter(include_in_schema=False)

    @api.get("/health")
    async def health():
        return _json(service.health())

    @api.get("/bootstrap")
    async def bootstrap(request: Request, project: str = None):
        return _json(service.bootstrap(current_user(request), project))

    @api.get("/day")
    async def day(request: Request, project: str = None, date: str = None):
        return _json(service.day(current_user(request), project, date))

    @api.post("/entries")
    async def add_entry(request: Request):
        return _json(service.add_entry(current_user(request), await _body(request)))

    @api.delete("/entries/{entry_id}")
    async def delete_entry(request: Request, entry_id: str, project: str = None):
        return _json(service.delete_entry(current_user(request), entry_id, project))

    @api.post("/analyse")
    async def analyse(request: Request):
        return _json(service.analyse(current_user(request), await _body(request)))

    @api.get("/bank")
    async def bank(request: Request, project: str = None):
        return _json(service.bank(current_user(request), project))

    @api.post("/coach")
    async def coach(request: Request):
        return _json(service.coach(current_user(request), await _body(request)))

    @api.post("/review")
    async def review(request: Request):
        return _json(service.review(current_user(request), await _body(request)))

    @api.get("/board")
    async def board(request: Request, days: int = 14):
        return _json(service.board(current_user(request), days))

    @api.get("/config")
    async def get_config(request: Request):
        return _json(service.get_config(current_user(request)))

    @api.put("/config")
    async def put_config(request: Request):
        return _json(service.put_config(current_user(request), await _body(request)))

    @api.get("/audit")
    async def audit_trail(request: Request, limit: int = 200):
        return _json(service.audit_trail(current_user(request), limit))

    @api.post("/ai-selftest")
    async def ai_selftest(request: Request):
        return _json(service.ai_selftest(current_user(request)))

    @api.post("/backup")
    async def backup(request: Request):
        return _json(service.make_backup(current_user(request)))

    # --- auto-review (v1.1). Cron calls with the shared secret; the desk's
    #     "Run now" button calls as the superuser. Both end in autoreview.run().
    @api.post("/auto-review")
    async def auto_review(request: Request):
        secret = request.headers.get("x-backlink-ops-cron") or ""
        if settings.CRON_SECRET and secret and _same(secret, settings.CRON_SECRET):
            from .. import autoreview
            return _json((200, {"run": autoreview.run(trigger="cron")}))
        return _json(service.auto_review_run(current_user(request)))

    @api.get("/auto-review")
    async def auto_review_status(request: Request):
        return _json(service.auto_review_status(current_user(request)))

    @page.get("/", response_class=HTMLResponse)
    async def desk():
        return HTMLResponse(service.page_html())

    return api, page


async def _body(request: Request):
    try:
        return await request.json()
    except Exception:
        return {}


def mount(app, logger):
    api, page = build_routers()
    app.include_router(api, prefix=settings.API_PREFIX)
    app.include_router(page, prefix=settings.URL_PREFIX)
    return True


def existing_paths(app):
    """Every path the host already serves, including routes reached through
    `include_router` and `Mount`.

    Flattening matters: the real dashboard mounts its own routers, and modern
    FastAPI keeps those as opaque wrapper objects in `app.routes` rather than
    expanding them. A guard that only read top-level `.path` would see an empty
    list and happily mount on top of an existing prefix.
    """
    return _walk(getattr(app, "routes", []) or [], "")


def _walk(routes, prefix, depth=0):
    out = set()
    if depth > 8:
        return out
    for r in routes:
        path = getattr(r, "path", None) or getattr(r, "path_format", None)
        children, child_prefix = None, ""

        # FastAPI >= 0.121 wraps an included router; the prefix lives on the
        # include context and the real routes on the router it wrapped.
        ctx = getattr(r, "include_context", None)
        if ctx is not None:
            child_prefix = getattr(ctx, "prefix", "") or ""
            inner = getattr(ctx, "included_router", None) or getattr(r, "original_router", None)
            children = getattr(inner, "routes", None)
        elif hasattr(r, "routes"):        # Starlette Mount / sub-application
            children = getattr(r, "routes", None)
            child_prefix = path or ""

        if path and not children:
            out.add(prefix + path)
        elif path and children:
            out.add(prefix + path)

        if children:
            out |= _walk(children, prefix + child_prefix, depth + 1)
    return out
