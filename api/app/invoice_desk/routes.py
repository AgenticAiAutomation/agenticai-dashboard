"""Invoice Desk — FastAPI routes. Translation only; rules live in service.py."""
import importlib
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import service
from .config import settings

_hook = None


def _load_hook():
    global _hook
    if _hook is None:
        try:
            mod, fn = settings.USER_HOOK.split(":")
            _hook = getattr(importlib.import_module(mod), fn)
        except Exception:
            _hook = False
    return _hook or None


def current_user(request: Request):
    hook = _load_hook()
    if not hook:
        return None
    try:
        u = hook(request)
    except Exception:
        return None
    return u if isinstance(u, dict) else None


def _json(res):
    status, payload = res
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _ip(request):
    fwd = request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0]
    return (fwd or (request.client.host if request.client else "")).strip()


_PAGES = {}


def _page(name):
    import os
    if name not in _PAGES:
        with open(os.path.join(os.path.dirname(__file__), "templates", name), encoding="utf-8") as fh:
            _PAGES[name] = fh.read()
    import json
    return (_PAGES[name].replace("__INV_API__", json.dumps(settings.API_PREFIX))
            .replace("__INV_TOKEN_KEY__", json.dumps(settings.TOKEN_STORAGE_KEY))
            .replace("__INV_LOGIN_URL__", json.dumps(settings.LOGIN_URL)))


def build_routers():
    api = APIRouter(tags=["invoice-desk"])
    page = APIRouter(include_in_schema=False)

    @api.get("/health")
    async def health():
        return _json(service.health())

    @api.get("/bootstrap")
    async def bootstrap(request: Request):
        return _json(service.bootstrap(current_user(request)))

    @api.get("/list")
    async def list_invoices(request: Request, view: str = "queue"):
        return _json(service.list_invoices(current_user(request), view))

    @api.post("/new")
    async def create(request: Request):
        return _json(service.create(current_user(request), await _body(request)))

    @api.post("/totals")
    async def totals(request: Request):
        return _json(service.totals(current_user(request), await _body(request)))

    @api.get("/settings")
    async def get_settings(request: Request):
        return _json(service.get_settings(current_user(request)))

    @api.put("/settings")
    async def put_settings(request: Request):
        return _json(service.put_settings(current_user(request), await _body(request)))

    @api.get("/links")
    async def links(request: Request):
        return _json(service.list_links(current_user(request)))

    @api.post("/links")
    async def create_link(request: Request):
        return _json(service.create_link(current_user(request), await _body(request)))

    @api.delete("/links/{token}")
    async def revoke_link(request: Request, token: str):
        return _json(service.revoke_link(current_user(request), token))

    @api.get("/audit")
    async def audit(request: Request, limit: int = 200):
        return _json(service.audit_trail(current_user(request), limit))

    # --- public: the client-facing form. Token-scoped, add-only.
    @api.get("/public/{token}")
    async def public_meta(token: str):
        return _json(service.public_meta(token))

    @api.post("/public/{token}")
    async def public_submit(request: Request, token: str):
        return _json(service.public_submit(token, await _body(request), _ip(request)))

    # --- one invoice
    @api.get("/inv/{inv_id}")
    async def get_invoice(request: Request, inv_id: str):
        return _json(service.get_invoice(current_user(request), inv_id))

    @api.put("/inv/{inv_id}")
    async def save(request: Request, inv_id: str):
        return _json(service.save(current_user(request), inv_id, await _body(request)))

    @api.delete("/inv/{inv_id}")
    async def delete(request: Request, inv_id: str):
        return _json(service.delete(current_user(request), inv_id))

    @api.post("/inv/{inv_id}/issue")
    async def issue(request: Request, inv_id: str):
        return _json(service.issue(current_user(request), inv_id, await _body(request)))

    @api.post("/inv/{inv_id}/void")
    async def void(request: Request, inv_id: str):
        return _json(service.void(current_user(request), inv_id, await _body(request)))

    @api.post("/inv/{inv_id}/duplicate")
    async def duplicate(request: Request, inv_id: str):
        return _json(service.duplicate(current_user(request), inv_id))

    @api.get("/inv/{inv_id}/pdf")
    async def pdf(request: Request, inv_id: str):
        status, body, fname = service.pdf_bytes(current_user(request), inv_id)
        if status != 200:
            return JSONResponse(body, status_code=status)
        return Response(body, media_type="application/pdf", headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(fname)}",
            "Cache-Control": "no-store"})

    # --- pages
    @page.get("/", response_class=HTMLResponse)
    async def desk():
        return HTMLResponse(_page("desk.html"), headers={"Cache-Control": "no-store"})

    @page.get("/f/{token}", response_class=HTMLResponse)
    async def fill(token: str):
        return HTMLResponse(_page("fill.html"), headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "Referrer-Policy": "no-referrer"})

    return api, page


def mount(app):
    api, page = build_routers()
    app.include_router(api, prefix=settings.API_PREFIX)
    app.include_router(page, prefix=settings.URL_PREFIX)
