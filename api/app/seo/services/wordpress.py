"""WordPress REST API client.

Publishing target is the WordPress install at /var/www/blog, served from
agenticaiautomation.co/blog/* (subfolder, not a subdomain).

Authentication uses an application password (WP_APP_USER / WP_APP_PASSWORD),
never the interactive login password.

The go-live gate in app.seo.golive decides whether a post is created with
status 'publish' or forced to 'draft'; this module only carries out the
decision it is handed.
"""
import base64
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.seo.services import ServiceUnavailable

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass
class WpPost:
    id: int
    link: str
    status: str
    slug: str


class WordPressClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        user: Optional[str] = None,
        app_password: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.WP_BASE_URL).rstrip("/")
        self.user = user or settings.WP_APP_USER
        self.app_password = app_password or settings.WP_APP_PASSWORD

    @property
    def configured(self) -> bool:
        return bool(self.user and self.app_password)

    def _require_config(self) -> None:
        if not self.configured:
            raise ServiceUnavailable(
                "wordpress",
                "WP_APP_USER and WP_APP_PASSWORD are not set. Generate an "
                "application password in WP admin and add both to api/.env.",
            )

    def _headers(self) -> Dict[str, str]:
        # Application passwords are issued with spaces; WP accepts them either way.
        token = base64.b64encode(
            f"{self.user}:{self.app_password}".encode()
        ).decode()
        return {"Authorization": f"Basic {token}"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/wp-json/wp/v2/{path.lstrip('/')}"

    # ---------------- connectivity ----------------
    def ping(self) -> Dict[str, Any]:
        """Verify the REST API answers and the credentials authenticate."""
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                anon = client.get(f"{self.base_url}/wp-json/")
                anon.raise_for_status()
                result: Dict[str, Any] = {
                    "rest_api_reachable": True,
                    "site_name": anon.json().get("name"),
                    "authenticated": False,
                }
                if self.configured:
                    me = client.get(
                        f"{self.base_url}/wp-json/wp/v2/users/me",
                        headers=self._headers(),
                    )
                    result["authenticated"] = me.status_code == 200
                    if me.status_code == 200:
                        body = me.json()
                        result["as_user"] = body.get("name")
                        result["capabilities_publish"] = bool(
                            body.get("capabilities", {}).get("publish_posts")
                        )
                    else:
                        result["auth_error"] = me.text[:300]
                return result
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("wordpress", f"{self.base_url} unreachable: {exc}")

    # ---------------- media ----------------
    def upload_media(self, filename: str, content: bytes, mime_type: str,
                     alt_text: Optional[str] = None) -> int:
        """Upload a featured image and return its WP media id."""
        self._require_config()
        headers = self._headers()
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        headers["Content-Type"] = mime_type
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                response = client.post(
                    self._url("media"), headers=headers, content=content)
                response.raise_for_status()
                media_id = response.json()["id"]
                if alt_text:
                    client.post(
                        self._url(f"media/{media_id}"),
                        headers=self._headers(),
                        json={"alt_text": alt_text},
                    ).raise_for_status()
                return media_id
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("wordpress", f"media upload failed: {exc}")

    # ---------------- posts ----------------
    def find_post_by_slug(self, slug: str) -> Optional[WpPost]:
        self._require_config()
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                response = client.get(
                    self._url("posts"),
                    headers=self._headers(),
                    params={"slug": slug, "status": "any", "per_page": 1},
                )
                response.raise_for_status()
                items = response.json()
                if not items:
                    return None
                item = items[0]
                return WpPost(id=item["id"], link=item["link"],
                              status=item["status"], slug=item["slug"])
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("wordpress", f"slug lookup failed: {exc}")

    def create_or_update_post(
        self,
        title: str,
        content_html: str,
        slug: str,
        status: str,
        excerpt: Optional[str] = None,
        featured_media: Optional[int] = None,
        post_id: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> WpPost:
        """Create a post, or update it in place when post_id is known."""
        self._require_config()
        payload: Dict[str, Any] = {
            "title": title,
            "content": content_html,
            "slug": slug,
            "status": status,
        }
        if excerpt:
            payload["excerpt"] = excerpt
        if featured_media:
            payload["featured_media"] = featured_media
        if meta:
            # RankMath reads rank_math_title / rank_math_description from post meta.
            payload["meta"] = meta

        path = f"posts/{post_id}" if post_id else "posts"
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                response = client.post(
                    self._url(path), headers=self._headers(), json=payload)
                response.raise_for_status()
                item = response.json()
                return WpPost(id=item["id"], link=item["link"],
                              status=item["status"], slug=item["slug"])
        except httpx.HTTPStatusError as exc:
            raise ServiceUnavailable(
                "wordpress",
                f"publish failed ({exc.response.status_code}): {exc.response.text[:400]}",
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("wordpress", f"publish failed: {exc}")


def get_client() -> WordPressClient:
    return WordPressClient()
