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

# --- Blog Playbook (flag status, saved builder blocks, advisory skim score).
#     Read-only and flagged (BLOG_PLAYBOOK_ENABLED / BLOG_PLAYBOOK_USERS).
#     Remove these two lines to remove the routes. See docs/BCP_AND_ROLLBACK.md.
from app.seo.routes import playbook as seo_playbook  # noqa: E402
app.include_router(seo_playbook.router)

# --- Backlink Ops (off-page SEO desk). Additive, feature-flagged.
#     Returns False and logs if disabled or unhealthy; never raises.
#     Remove these two lines to uninstall. See docs/BCP_AND_ROLLBACK.md.
from app.backlink_ops import register as register_backlink_ops
register_backlink_ops(app)

# --- WhatsApp leads desk (CRM over wa-funnel's leads). Additive, flagged.
#     Off unless WA_LEADS_ENABLED=1. Returns False and logs if the funnel's
#     database is unreachable; never raises. Remove these two lines to
#     uninstall. See docs/WA_LEADS.md.
from app.wa_leads import register as register_wa_leads  # noqa: E402
register_wa_leads(app)

# --- Invoice Desk (client fill links → review queue → PDF). Additive,
#     feature-flagged (INVOICE_DESK_ENABLED), own SQLite file, never raises.
#     Remove these two lines to uninstall. See docs/INVOICE_DESK.md.
from app.invoice_desk import register as register_invoice_desk
register_invoice_desk(app)


@app.get("/")
def root():
    return {"message": "AgenticAI Dashboard API", "version": "2.0.0",
            "modules": ["dashboard", "seo-operations"]}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
