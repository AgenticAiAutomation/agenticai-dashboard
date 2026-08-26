from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    # Spec: 8 hours idle then force re-login. The access token carries both an
    # absolute expiry and a last-activity claim; see app.auth.
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SESSION_IDLE_TIMEOUT_MINUTES: int = 480
    INITIAL_OWNER_EMAIL: str
    INITIAL_OWNER_PASSWORD: str
    CORS_ORIGINS: str

    # --- SEO module ---
    # Absolute path to the go-live approval file. Until it exists and is dated
    # within the last 24h, WordPress publishes are forced to status=draft.
    SEO_LIVE_APPROVAL_FILE: str = "/var/www/agenticai-dashboard/SEO_LIVE_APPROVED.txt"

    # --- Publishing output ---
    # A finished article is written as JSON into SITE_CONTENT_DIR with its
    # featured image copied into SITE_MEDIA_DIR. Both live under the dashboard
    # and are owned by it — nothing outside the dashboard is written to.
    #
    # This is deliberately the entire publish path: no CMS, no second database,
    # and no credentials that can be unset. Publishing previously called the
    # WordPress REST API and failed with "WP_APP_USER and WP_APP_PASSWORD are
    # not set" on a server where WordPress had never been installed, which
    # blocked every finished article indefinitely.
    #
    # Whichever system eventually serves these files reads this directory.
    # That is a separate decision and does not belong in the publish path.
    SITE_CONTENT_DIR: str = "/var/www/agenticai-dashboard/published/articles"
    SITE_MEDIA_DIR: str = "/var/www/agenticai-dashboard/published/media"
    SITE_BLOG_BASE_URL: str = "https://agenticaiautomation.co/blog"

    # IndexNow. The key file is already served from the site root; this must be
    # the same value or submissions are rejected. Empty disables submission
    # entirely rather than sending unsigned requests.
    INDEXNOW_KEY: Optional[str] = None
    INDEXNOW_HOST: str = "agenticaiautomation.co"

    # WordPress REST API. Retained so an existing install can still be targeted,
    # but it is no longer part of the publish path — see app.seo.services.publisher.
    WP_BASE_URL: str = "https://agenticaiautomation.co/blog"
    WP_APP_USER: Optional[str] = None
    WP_APP_PASSWORD: Optional[str] = None

    # Anthropic — draft generation, alt captions, audit interpretation.
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    # Budget cap in INR per UTC day across all Claude calls in this module.
    SEO_DAILY_BUDGET_INR: float = 500.0

    # MinIO / S3-compatible object store for featured images.
    MINIO_ENDPOINT: Optional[str] = None
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    MINIO_BUCKET: str = "seo-images"
    MINIO_SECURE: bool = True

    # AI-detection provider for scoring parameter `ai_detection` (8 points, the
    # heaviest single check). Supported: "originality" or "gptzero". Leave
    # AI_DETECTION_PROVIDER unset to skip the parameter rather than score it
    # zero — see app.seo.services.scoring for why skipping is the right default.
    AI_DETECTION_PROVIDER: Optional[str] = None
    AI_DETECTION_API_KEY: Optional[str] = None
    # Percentage of AI-generated text above which the parameter scores zero.
    AI_DETECTION_MAX_PERCENT: float = 20.0

    # Self-hosted LanguageTool (Docker, port 8010).
    LANGUAGETOOL_URL: str = "http://127.0.0.1:8010"
    # Reused from Concierge — bge-m3 embeddings for semantic coverage scoring.
    EMBEDDER_URL: Optional[str] = None

    # Google service accounts (JSON key paths, kept out of git in secrets/).
    GSC_SERVICE_ACCOUNT_JSON: Optional[str] = None
    GSC_SITE_URL: str = "https://agenticaiautomation.co/"
    GA4_SERVICE_ACCOUNT_JSON: Optional[str] = None
    GA4_PROPERTY_ID: Optional[str] = None

    SERPAPI_KEY: Optional[str] = None
    # Shared secret required by /api/seo/cron/* so only the box can trigger them.
    CRON_SECRET: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(',')]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
