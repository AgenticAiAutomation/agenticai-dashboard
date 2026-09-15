"""Flask adapter — kept so the same module can mount on a Flask host.

The AgenticAI dashboard is FastAPI; this exists so the package is not tied to
one framework, and so the smoke test can prove both adapters return identical
answers from the same service layer.
"""
from flask import Blueprint, Response, request

from .. import service
from ..config import settings
from ..identity import normalise
from . import _userhook as uh


def current_user():
    hook = uh.load_hook()
    if hook:
        try:
            raw = hook(request)
        except Exception:
            raw = None
        u = normalise(uh.as_dict(raw))
        if u:
            return u

    try:
        from flask_login import current_user as flask_login_user  # type: ignore
        if getattr(flask_login_user, "is_authenticated", False):
            u = normalise(uh.as_dict(flask_login_user))
            if u:
                return u
    except Exception:
        pass

    try:
        from flask import g, session
        raw = getattr(g, "user", None)
        if raw is None:
            for key in ("user", "current_user", "auth_user"):
                if isinstance(session.get(key), dict):
                    raw = session[key]
                    break
            else:
                email = session.get("user_email") or session.get("email")
                if email:
                    raw = {"email": email, "name": session.get("user_name") or email,
                           "role": session.get("role"), "roles": session.get("roles")}
        u = normalise(uh.as_dict(raw))
        if u:
            return u
    except Exception:
        pass

    u = normalise(uh.from_token(request.headers.get("Authorization"), request.cookies))
    if u:
        return u
    return normalise(uh.anonymous())


def _json(result):
    import json
    status, payload = result
    return Response(json.dumps(payload, default=str), status=status,
                    mimetype="application/json")


def build_blueprints():
    api = Blueprint("backlink_ops_api", __name__)
    page = Blueprint("backlink_ops", __name__)

    @api.get("/health")
    def health():
        return _json(service.health())

    @api.get("/bootstrap")
    def bootstrap():
        return _json(service.bootstrap(current_user(), request.args.get("project")))

    @api.get("/day")
    def day():
        return _json(service.day(current_user(), request.args.get("project"),
                                 request.args.get("date")))

    @api.post("/entries")
    def add_entry():
        return _json(service.add_entry(current_user(), request.get_json(silent=True)))

    @api.delete("/entries/<entry_id>")
    def delete_entry(entry_id):
        return _json(service.delete_entry(current_user(), entry_id,
                                          request.args.get("project")))

    @api.post("/analyse")
    def analyse():
        return _json(service.analyse(current_user(), request.get_json(silent=True)))

    @api.get("/bank")
    def bank():
        return _json(service.bank(current_user(), request.args.get("project")))

    @api.post("/coach")
    def coach():
        return _json(service.coach(current_user(), request.get_json(silent=True)))

    @api.post("/review")
    def review():
        return _json(service.review(current_user(), request.get_json(silent=True)))

    @api.get("/board")
    def board():
        return _json(service.board(current_user(), request.args.get("days", 14)))

    @api.get("/config")
    def get_config():
        return _json(service.get_config(current_user()))

    @api.put("/config")
    def put_config():
        return _json(service.put_config(current_user(), request.get_json(silent=True)))

    @api.get("/audit")
    def audit_trail():
        return _json(service.audit_trail(current_user(), request.args.get("limit", 200)))

    @api.post("/ai-selftest")
    def ai_selftest():
        return _json(service.ai_selftest(current_user()))

    @api.post("/backup")
    def backup():
        return _json(service.make_backup(current_user()))

    @api.post("/auto-review")
    def auto_review():
        import hmac
        secret = request.headers.get("X-Backlink-Ops-Cron") or ""
        if settings.CRON_SECRET and secret and \
                hmac.compare_digest(secret.encode(), settings.CRON_SECRET.encode()):
            from .. import autoreview
            return _json((200, {"run": autoreview.run(trigger="cron")}))
        return _json(service.auto_review_run(current_user()))

    @api.get("/auto-review")
    def auto_review_status():
        return _json(service.auto_review_status(current_user()))

    @page.get("/")
    def desk():
        return Response(service.page_html(), mimetype="text/html")

    return api, page


def mount(app, logger):
    api, page = build_blueprints()
    app.register_blueprint(page, url_prefix=settings.URL_PREFIX)
    app.register_blueprint(api, url_prefix=settings.API_PREFIX)
    return True


def existing_paths(app):
    return {r.rule for r in app.url_map.iter_rules()}
