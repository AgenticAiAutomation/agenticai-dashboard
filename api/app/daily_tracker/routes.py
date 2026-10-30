"""Daily Tracker + Idea Board — FastAPI routes. Thin: every rule is in service.py.

Identity comes from the same non-raising hook Invoice Desk uses (the
dashboard's bearer token, read from the Authorization header).
"""
import importlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from . import bigideas, service, taskmgr, worktime
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

    # ---------------------------------------------------- task manager (T7)
    @tasks.get("/items")
    async def list_items(request: Request, scope: str = "mine", user_id: str = None,
                         project_id: str = None, status: str = None, due_before: str = None):
        return _json(taskmgr.list_tasks(current_user(request), scope, user_id, project_id, status, due_before))

    @tasks.post("/items")
    async def create_item(request: Request):
        return _json(taskmgr.create_task(current_user(request), await _body(request)))

    @tasks.get("/items/{task_id}")
    async def get_item(request: Request, task_id: int):
        return _json(taskmgr.get_task(current_user(request), task_id))

    @tasks.put("/items/{task_id}")
    async def update_item(request: Request, task_id: int):
        return _json(taskmgr.update_task(current_user(request), task_id, await _body(request)))

    @tasks.delete("/items/{task_id}")
    async def delete_item(request: Request, task_id: int):
        return _json(taskmgr.delete_task(current_user(request), task_id))

    @tasks.post("/items/{task_id}/status")
    async def item_status(request: Request, task_id: int):
        return _json(taskmgr.set_status(current_user(request), task_id, await _body(request)))

    @tasks.post("/items/{task_id}/approve")
    async def item_approve(request: Request, task_id: int):
        return _json(taskmgr.approve(current_user(request), task_id, await _body(request)))

    @tasks.post("/items/{task_id}/progress")
    async def item_progress(request: Request, task_id: int):
        return _json(taskmgr.add_progress(current_user(request), task_id, await _body(request)))

    @tasks.post("/items/{task_id}/comments")
    async def item_comment(request: Request, task_id: int):
        return _json(taskmgr.add_comment(current_user(request), task_id, await _body(request)))

    @tasks.post("/items/{task_id}/links")
    async def item_link(request: Request, task_id: int):
        return _json(taskmgr.add_link(current_user(request), task_id, await _body(request)))

    @tasks.post("/items/{task_id}/checklist")
    async def item_check_add(request: Request, task_id: int):
        return _json(taskmgr.add_checklist(current_user(request), task_id, await _body(request)))

    @tasks.put("/items/{task_id}/checklist/{item_id}")
    async def item_check(request: Request, task_id: int, item_id: int):
        return _json(taskmgr.toggle_checklist(current_user(request), task_id, item_id, await _body(request)))

    @tasks.get("/people")
    async def people(request: Request):
        return _json(taskmgr.people(current_user(request)))

    @tasks.get("/plan")
    async def plan(request: Request, user_id: str = None, month: str = None):
        return _json(taskmgr.plan(current_user(request), user_id, month))

    @tasks.put("/plan")
    async def plan_set(request: Request):
        return _json(taskmgr.set_target(current_user(request), await _body(request)))

    @tasks.put("/plan/split")
    async def plan_split(request: Request):
        return _json(taskmgr.set_split(current_user(request), await _body(request)))

    @tasks.post("/plan/template")
    async def plan_template(request: Request):
        return _json(taskmgr.apply_template(current_user(request), await _body(request)))

    @tasks.get("/templates")
    async def templates(request: Request):
        return _json(taskmgr.templates(current_user(request)))

    @tasks.put("/templates")
    async def templates_put(request: Request):
        return _json(taskmgr.put_templates(current_user(request), await _body(request)))

    @tasks.put("/leave")
    async def leave_set(request: Request):
        return _json(taskmgr.set_leave(current_user(request), await _body(request)))

    @tasks.post("/leave/remove")
    async def leave_remove(request: Request):
        return _json(taskmgr.set_leave(current_user(request), await _body(request), remove=True))

    @tasks.get("/rag")
    async def rag(request: Request, user_id: str = None):
        return _json(taskmgr.my_rag(current_user(request), user_id))

    @tasks.get("/rag/team")
    async def rag_team(request: Request):
        return _json(taskmgr.team_rag(current_user(request)))

    @tasks.put("/rag-settings")
    async def rag_settings(request: Request):
        return _json(taskmgr.put_rag_settings(current_user(request), await _body(request)))

    @tasks.get("/mirror")
    async def mirror(request: Request, user_id: str = None, month: str = None):
        return _json(taskmgr.mirror(current_user(request), user_id, month))

    @tasks.put("/mirror-settings")
    async def mirror_settings(request: Request):
        return _json(taskmgr.put_mirror_settings(current_user(request), await _body(request)))

    @tasks.get("/tiers")
    async def get_tiers(request: Request):
        return _json(taskmgr.get_tiers(current_user(request)))

    @tasks.put("/tiers")
    async def put_tiers(request: Request):
        return _json(taskmgr.put_tiers(current_user(request), await _body(request)))

    @tasks.get("/rewards")
    async def rewards(request: Request, month: str = None):
        return _json(taskmgr.rewards(current_user(request), month))

    @tasks.post("/rewards/approve")
    async def rewards_approve(request: Request):
        return _json(taskmgr.approve_rewards(current_user(request), await _body(request)))

    @tasks.get("/rewards.csv")
    async def rewards_csv(request: Request, month: str = None):
        status, out = taskmgr.rewards_csv(current_user(request), month)
        if status != 200:
            return _json((status, out))
        return Response(out, media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="rewards-{month or "month"}.csv"',
            "Cache-Control": "no-store"})

    # ---------------------------------------------------- tasks v2: timer, proof, road blockers
    @tasks.get("/v2/state")
    async def v2_state(request: Request):
        return _json(worktime.state(current_user(request)))

    @tasks.post("/v2/tasks")
    async def v2_create(request: Request):
        return _json(worktime.create_task(current_user(request), await _body(request)))

    @tasks.post("/v2/tasks/{task_id}/start")
    async def v2_start(request: Request, task_id: int):
        return _json(worktime.start(current_user(request), task_id))

    @tasks.post("/v2/pause")
    async def v2_pause(request: Request):
        return _json(worktime.pause(current_user(request)))

    @tasks.post("/v2/break")
    async def v3_break(request: Request):
        return _json(worktime.take_break(current_user(request), await _body(request)))

    @tasks.post("/v2/session/end")
    async def v2_end_session(request: Request):
        return _json(worktime.end_session(current_user(request), await _body(request)))

    @tasks.post("/v2/day/start")
    async def v3_day_start(request: Request):
        return _json(worktime.start_day(current_user(request)))

    @tasks.post("/v2/day/end")
    async def v3_day_end(request: Request):
        return _json(worktime.end_day(current_user(request)))

    @tasks.post("/v2/day/reopen")
    async def v3_day_reopen(request: Request):
        return _json(worktime.reopen_day(current_user(request), await _body(request)))

    @tasks.post("/v2/day/set-end")
    async def v3_day_set_end(request: Request):
        return _json(worktime.set_day_end(current_user(request), await _body(request)))

    @tasks.post("/v2/hours/week")
    async def v3_week_hours(request: Request):
        return _json(worktime.set_week_hours(current_user(request), await _body(request)))

    @tasks.post("/v2/hours/allowance")
    async def v3_allowance(request: Request):
        return _json(worktime.set_allowance(current_user(request), await _body(request)))

    @tasks.get("/v2/ideas")
    async def v3_ideas(request: Request):
        return _json(bigideas.board(current_user(request)))

    @tasks.post("/v2/ideas")
    async def v3_idea_submit(request: Request):
        return _json(bigideas.submit(current_user(request), await _body(request)))

    @tasks.post("/v2/ideas/{idea_id}/decide")
    async def v3_idea_decide(request: Request, idea_id: int):
        return _json(bigideas.decide(current_user(request), idea_id, await _body(request)))

    @tasks.post("/v2/ideas/employee-of-month")
    async def v3_idea_eom(request: Request):
        return _json(bigideas.pick_employee_of_month(current_user(request), await _body(request)))

    @tasks.post("/v2/hours/day")
    async def v3_day_hours(request: Request):
        return _json(worktime.set_day_hours(current_user(request), await _body(request)))

    @tasks.post("/v2/routines")
    async def v3_routine_create(request: Request):
        return _json(worktime.create_routine(current_user(request), await _body(request)))

    @tasks.post("/v2/routines/{routine_id}/active")
    async def v3_routine_active(request: Request, routine_id: int):
        return _json(worktime.set_routine_active(current_user(request), routine_id, await _body(request)))

    @tasks.post("/v2/routines/{routine_id}/start")
    async def v3_routine_start(request: Request, routine_id: int):
        return _json(worktime.start_routine(current_user(request), routine_id))

    @tasks.post("/v2/tasks/{task_id}/complete")
    async def v2_complete(request: Request, task_id: int):
        return _json(worktime.complete(current_user(request), task_id, await _body(request)))

    @tasks.post("/v2/tasks/{task_id}/block")
    async def v2_block(request: Request, task_id: int):
        return _json(worktime.block(current_user(request), task_id, await _body(request)))

    @tasks.post("/v2/tasks/{task_id}/unblock")
    async def v2_unblock(request: Request, task_id: int):
        return _json(worktime.unblock(current_user(request), task_id))

    @tasks.post("/v2/holds/{hold_id}/decide")
    async def v2_decide(request: Request, hold_id: int):
        return _json(worktime.decide_hold(current_user(request), hold_id, await _body(request)))

    @tasks.post("/v2/proof")
    async def v2_proof(request: Request):
        return _json(worktime.add_proof(current_user(request), await _body(request)))

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
