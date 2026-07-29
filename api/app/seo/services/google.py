"""Google Search Console + Analytics 4 clients.

Both authenticate with a service account JSON key kept outside git (secrets/).
Neither is required for the dashboard to boot: when the key is missing the
callers fall back to whatever is already in seo_gsc_daily.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.config import settings
from app.seo.services import ServiceUnavailable

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _credentials(path: Optional[str], scopes: List[str], service: str):
    if not path:
        raise ServiceUnavailable(
            service,
            f"no service account JSON configured. Put the key in secrets/ and set the "
            f"path in api/.env.",
        )
    try:
        from google.oauth2 import service_account
    except ImportError:
        raise ServiceUnavailable(service, "google-auth is not installed")
    try:
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)
    except OSError as exc:
        raise ServiceUnavailable(service, f"cannot read {path}: {exc}")


class SearchConsole:
    def __init__(self, site_url: Optional[str] = None):
        self.site_url = site_url or settings.GSC_SITE_URL

    @property
    def configured(self) -> bool:
        return bool(settings.GSC_SERVICE_ACCOUNT_JSON)

    def _service(self):
        creds = _credentials(settings.GSC_SERVICE_ACCOUNT_JSON, GSC_SCOPES, "gsc")
        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise ServiceUnavailable("gsc", "google-api-python-client is not installed")
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    def verify(self) -> Dict[str, Any]:
        """Confirm the service account can actually see the property."""
        service = self._service()
        sites = service.sites().list().execute().get("siteEntry", [])
        urls = [s["siteUrl"] for s in sites]
        return {
            "authenticated": True,
            "sites": urls,
            "target_site_accessible": self.site_url in urls,
        }

    def query(self, start: date, end: date,
              dimensions: Optional[List[str]] = None,
              row_limit: int = 5000) -> List[Dict[str, Any]]:
        """Search Analytics rows. GSC data lags ~2 days; callers offset for that."""
        service = self._service()
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions or ["date", "query", "page"],
            "rowLimit": row_limit,
        }
        response = service.searchanalytics().query(
            siteUrl=self.site_url, body=body).execute()

        rows = []
        for row in response.get("rows", []):
            keys = row.get("keys", [])
            entry = {dim: keys[i] if i < len(keys) else None
                     for i, dim in enumerate(body["dimensions"])}
            entry.update({
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0.0),
                "position": row.get("position", 0.0),
            })
            rows.append(entry)
        return rows


class Analytics4:
    def __init__(self, property_id: Optional[str] = None):
        self.property_id = property_id or settings.GA4_PROPERTY_ID

    @property
    def configured(self) -> bool:
        return bool(settings.GA4_SERVICE_ACCOUNT_JSON and self.property_id)

    def _client(self):
        creds = _credentials(settings.GA4_SERVICE_ACCOUNT_JSON, GA4_SCOPES, "ga4")
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
        except ImportError:
            raise ServiceUnavailable(
                "ga4", "google-analytics-data is not installed")
        return BetaAnalyticsDataClient(credentials=creds)

    def verify(self) -> Dict[str, Any]:
        rows = self.organic_sessions(date.today() - timedelta(days=7), date.today())
        return {"authenticated": True, "property_id": self.property_id, "rows": len(rows)}

    def organic_sessions(self, start: date, end: date) -> List[Dict[str, Any]]:
        if not self.property_id:
            raise ServiceUnavailable("ga4", "GA4_PROPERTY_ID is not set")
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )

        client = self._client()
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[Dimension(name="date"), Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
            date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        )
        response = client.run_report(request)
        return [
            {
                "date": row.dimension_values[0].value,
                "channel": row.dimension_values[1].value,
                "sessions": int(row.metric_values[0].value or 0),
                "users": int(row.metric_values[1].value or 0),
            }
            for row in response.rows
        ]
