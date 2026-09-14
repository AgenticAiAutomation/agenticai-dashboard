"""A stand-in for agenticai-dashboard, close enough to prove the integration.

FastAPI, JWT-ish auth via middleware that sets request.state.user, roles
admin / seo_lead / viewer, and the routes that already exist on the real
dashboard — including /api/seo/backlinks, which must NOT be mistaken for a
collision with /api/seo/backlink-ops.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

USERS = {
    "jai":    {"id": 1, "name": "Jai",              "email": "jai.prajapati91@gmail.com", "role": "admin"},
    "lead":   {"id": 2, "name": "SEO Associate 1",  "email": "seo1@agenticai.co",         "role": "seo_lead"},
    "lead2":  {"id": 3, "name": "SEO Associate 2",  "email": "seo2@agenticai.co",         "role": "seo_lead"},
    "viewer": {"id": 4, "name": "Intern",           "email": "intern@agenticai.co",       "role": "viewer"},
}


def make_app():
    app = FastAPI(title="AgenticAI Dashboard API")

    @app.middleware("http")
    async def auth(request: Request, call_next):
        who = request.headers.get("x-test-user")
        request.state.user = USERS.get(who)
        return await call_next(request)

    # --- routes that already exist and must keep working ------------------
    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/seo/backlinks")
    async def list_backlinks():
        return {"rows": [], "source": "pre-existing seo_backlinks table"}

    @app.post("/api/seo/backlinks")
    async def add_backlink():
        return JSONResponse({"created": True, "source": "pre-existing"}, status_code=201)

    @app.get("/api/seo/backlinks/haro")
    async def haro():
        return {"haro": True}

    @app.get("/api/articles")
    async def articles():
        return {"articles": [], "source": "pre-existing article pipeline"}

    @app.post("/api/articles/publish")
    async def publish():
        return {"published": True}

    @app.get("/api/team/scoreboard")
    async def scoreboard():
        return {"team": []}

    return app
