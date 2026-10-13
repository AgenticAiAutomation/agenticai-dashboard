"""Daily Tracker + Idea Board — FastAPI routes. Thin: every rule is in service.py.

Identity comes from the same non-raising hook Invoice Desk uses (the
dashboard's bearer token, read from the Authorization header).
"""
import importlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

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
    tasks = APIRouter(tags=["daily-tracker"])
    ideas = APIRouter(tags=["idea-board"])

    @tasks.get("/status")
    async def status(request: Request):
        return _json(service.status(current_user(request)))

    @tasks.get("/work-types")
    async def work_types(request: Request):
        return _json(service.work_types(current_user(request)))

    @tasks.put("/work-types")
    async def put_work_types(request: Request):
        return _json(service.put_work_types(current_user(request), await _body(request)))

    @tasks.post("/logs")
    async def create_log(request: Request):
        return _json(service.create_log(current_user(request), await _body(request)))

    @tasks.get("/logs")
    async def list_logs(request: Request, date: str = None, project_id: str = None,
                        user_id: str = None):
        return _json(service.list_logs(current_user(request), date, project_id, user_id))

    @tasks.put("/logs/{log_id}")
    async def update_log(request: Request, log_id: int):
        return _json(service.update_log(current_user(request), log_id, await _body(request)))

    @tasks.delete("/logs/{log_id}")
    async def delete_log(request: Request, log_id: int):
        return _json(service.delete_log(current_user(request), log_id))

    @tasks.post("/logs/review-bulk")
    async def review_bulk(request: Request):
        return _json(service.review_bulk(current_user(request), await _body(request)))

    @tasks.post("/logs/{log_id}/review")
    async def review(request: Request, log_id: int):
        return _json(service.review(current_user(request), log_id, await _body(request)))

    @tasks.get("/review-queue")
    async def review_queue(request: Request):
        return _json(service.review_queue(current_user(request)))

    @tasks.get("/summary")
    async def summary(request: Request, range: str = "day", user_id: str = None):  # noqa: A002
        return _json(service.summary(current_user(request), range, user_id))

    @tasks.get("/report")
    async def report(request: Request, start: str = None, end: str = None):
        return _json(service.report(current_user(request), start, end))

    @tasks.get("/export.csv")
    async def export_csv(request: Request, start: str = None, end: str = None):
        status, out = service.export_csv(current_user(request), start, end)
        if status != 200:
            return _json((status, out))
        return Response(out, media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="daily-tracker-{start or "month"}.csv"',
            "Cache-Control": "no-store"})

    @tasks.post("/import")
    async def import_csv(request: Request):
        return _json(service.import_csv(current_user(request), await _body(request)))

    @tasks.put("/settings")
    async def put_settings(request: Request):
        return _json(service.put_settings(current_user(request), await _body(request)))

    @tasks.put("/targets")
    async def set_target(request: Request):
        return _json(service.set_target(current_user(request), await _body(request)))

    @ideas.get("")
    async def list_ideas(request: Request, project_id: str = None, status: str = None,
                         month: str = None):
        return _json(service.list_ideas(current_user(request), project_id, status, month))

    @ideas.post("")
    async def create_idea(request: Request):
        return _json(service.create_idea(current_user(request), await _body(request)))

    @ideas.post("/{idea_id}/status")
    async def idea_status(request: Request, idea_id: int):
        return _json(service.idea_status(current_user(request), idea_id, await _body(request)))

    @ideas.post("/{idea_id}/vote")
    async def vote(request: Request, idea_id: int):
        return _json(service.vote(current_user(request), idea_id))

    return tasks, ideas


def mount(app):
    tasks, ideas = build()
    app.include_router(tasks, prefix=settings.TASKS_PREFIX)
    app.include_router(ideas, prefix=settings.IDEAS_PREFIX)
    return True
