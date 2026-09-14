import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import articles, auth, keywords, metrics, tasks, users
from app.seo.routes import (
    articles as seo_articles,
    calendar as seo_calendar,
    cron as seo_cron,
    dashboard as seo_dashboard,
    infra as seo_infra,
    pull_requests as seo_pull_requests,
    recommendations as seo_recommendations,
)

app = FastAPI(
    title="AgenticAI Dashboard API",
    version="2.0.0",
    description="Team-facing SEO ops dashboard for AgenticAiAutomation, "
                "including the SEO Operations module (Product C).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Existing dashboard
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(keywords.router)
app.include_router(articles.router)
app.include_router(tasks.router)
app.include_router(metrics.router)

# SEO Operations module — everything under /api/seo
app.include_router(seo_infra.router)
app.include_router(seo_articles.router)
app.include_router(seo_pull_requests.router)
app.include_router(seo_calendar.router)
app.include_router(seo_dashboard.router)
app.include_router(seo_recommendations.router)
app.include_router(seo_cron.router)

# --- Backlink Ops (off-page SEO desk). Additive, feature-flagged.
#     Returns False and logs if disabled or unhealthy; never raises.
#     Remove these lines to uninstall. See docs/BCP_AND_ROLLBACK.md.
#     Explicit logger: FastAPI has no app.logger (that's Flask-only), and this
#     app configures no handler for a bare "backlink_ops" logger, so without
#     this the module's own mount/failure line would be silently swallowed.
#     uvicorn.error is the logger uvicorn's own startup lines already use.
from app.backlink_ops import register as register_backlink_ops
register_backlink_ops(app, logger=logging.getLogger("uvicorn.error"))


@app.get("/")
def root():
    return {"message": "AgenticAI Dashboard API", "version": "2.0.0",
            "modules": ["dashboard", "seo-operations"]}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
