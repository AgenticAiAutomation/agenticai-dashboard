"""Follow-ups — FastAPI routes. Thin: the rules are in service.py."""
import importlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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
        return await request.json()
    except Exception:
        return {}


def build():
    r = APIRouter(tags=["followups"])

    @r.get("/status")
    async def status(request: Request):
        return _json(service.status(current_user(request)))

    @r.get("/board")
    async def board(request: Request, days: int = 14):
        return _json(service.board(current_user(request), days))

    @r.get("/calendar")
    async def calendar(request: Request, start: str = None, end: str = None):
        return _json(service.calendar(current_user(request), start, end))

    @r.post("/items")
    async def create(request: Request):
        return _json(service.create_followup(current_user(request), await _body(request)))

    @r.put("/items/{fid}")
    async def update(request: Request, fid: int):
        return _json(service.update_followup(current_user(request), fid, await _body(request)))

    @r.post("/items/{fid}/done")
    async def done(request: Request, fid: int):
        return _json(service.done(current_user(request), fid, await _body(request)))

    @r.post("/items/{fid}/snooze")
    async def snooze(request: Request, fid: int):
        return _json(service.snooze(current_user(request), fid, await _body(request)))

    @r.get("/projects")
    async def projects(request: Request):
        return _json(service.list_projects(current_user(request)))

    @r.post("/projects")
    async def project_new(request: Request):
        return _json(service.create_project(current_user(request), await _body(request)))

    @r.put("/projects/{pid}")
    async def project_edit(request: Request, pid: int):
        return _json(service.update_project(current_user(request), pid, await _body(request)))

    @r.get("/contacts")
    async def contacts(request: Request, q: str = None):
        return _json(service.list_contacts(current_user(request), q))

    @r.post("/contacts")
    async def contact_new(request: Request):
        return _json(service.create_contact(current_user(request), await _body(request)))

    @r.get("/contacts/{cid}")
    async def contact(request: Request, cid: int):
        return _json(service.get_contact(current_user(request), cid))

    @r.put("/contacts/{cid}")
    async def contact_edit(request: Request, cid: int):
        return _json(service.update_contact(current_user(request), cid, await _body(request)))

    @r.post("/contacts/{cid}/notes")
    async def note(request: Request, cid: int):
        return _json(service.add_note(current_user(request), cid, await _body(request)))

    return r


def mount(app):
    app.include_router(build(), prefix=settings.API_PREFIX)
    return True
