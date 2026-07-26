from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes import auth, users, keywords, articles, tasks, metrics

app = FastAPI(
    title="AgenticAI Dashboard API",
    version="1.0.0",
    description="Team-facing SEO ops dashboard for AgenticAiAutomation"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(keywords.router)
app.include_router(articles.router)
app.include_router(tasks.router)
app.include_router(metrics.router)


@app.get("/")
def root():
    return {"message": "AgenticAI Dashboard API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
