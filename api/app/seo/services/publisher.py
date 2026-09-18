"""Publishing output: a finished article becomes files the dashboard owns.

Replaces the WordPress REST path, which failed with "WP_APP_USER and
WP_APP_PASSWORD are not set" on a server where WordPress had never been
installed — blocking every finished article. An article now becomes one JSON
file in SITE_CONTENT_DIR plus its featured image in SITE_MEDIA_DIR. No CMS, no
PHP, no application password, no plugin to keep patched, and nothing in the
publish path that can be left unconfigured.

Whichever system eventually serves these files reads that directory. This
module has no opinion about it and writes nothing outside the dashboard.

Two properties matter here:

Atomicity. Each file is written to a temporary name in the same directory and
then os.replace'd into place, which is atomic on POSIX. A reader can never
observe a half-written article, and a crash mid-publish leaves the previous
version intact rather than a truncated file.

Reversibility. unpublish() removes the article and its image, so taking a post
down is the same one action as putting it up — the state on disk is always
exactly the set of published articles.
"""
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.seo.services import ServiceUnavailable, storage

# Bumped when the JSON contract changes, so the site can refuse to render a
# file it does not understand rather than silently dropping fields.
CONTENT_SCHEMA_VERSION = 1


@dataclass
class PublishedArticle:
    slug: str
    url: str
    path: str
    image_path: Optional[str]
    bytes_written: int


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
        # The web server reads these as a different user than the API writes as.
        os.chmod(path, 0o755)
    except OSError as exc:
        raise ServiceUnavailable(
            "publisher",
            f"cannot create {path} ({exc.strerror}). The API runs as its service "
            f"account, so that account needs ownership: "
            f"mkdir -p {path} && chown -R www-data:www-data {path}",
        )


def _write_atomic(path: str, payload: bytes) -> None:
    directory = os.path.dirname(path)
    # The temp file must share a filesystem with the target or os.replace is
    # not atomic, so it is created in the destination directory.
    handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # mkstemp creates 0600. Published articles and their images are public
        # content served by the web server as a different user, so they need to
        # be world-readable or every publish 404s on the image.
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise ServiceUnavailable(
            "publisher", f"could not write {path} ({exc.strerror})")


def _copy_image(article_id: str, slug: str, image_path: Optional[str]) -> Optional[str]:
    """Copy the featured image into the published media directory.

    Returns the path relative to that directory, which is what a renderer
    resolves against, or None when the article has no image.
    """
    if not image_path:
        return None

    content, mime = storage.get_object(image_path)
    extension = {"image/png": ".png", "image/jpeg": ".jpg",
                 "image/webp": ".webp"}.get(mime, ".jpg")

    _ensure_dir(settings.SITE_MEDIA_DIR)
    filename = f"{slug}{extension}"
    destination = os.path.join(settings.SITE_MEDIA_DIR, filename)
    _write_atomic(destination, content)
    return f"blog/{filename}"


def publish(
    *,
    article_id: str,
    slug: str,
    title: str,
    html: str,
    meta_title: Optional[str],
    meta_description: Optional[str],
    primary_keyword: str,
    faqs: List[Dict[str, Any]],
    featured_image_path: Optional[str],
    featured_image_alt: Optional[str],
    author: str,
    from_author_story: Optional[str],
    published_at: Optional[datetime] = None,
    is_draft: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> PublishedArticle:
    """Write one article to the output directory. Overwrites any previous version."""
    _ensure_dir(settings.SITE_CONTENT_DIR)

    image_relative = _copy_image(article_id, slug, featured_image_path)
    now = datetime.now(timezone.utc)

    def as_utc(value: datetime) -> str:
        """Always emit UTC.

        The database returns timestamps in the server's local zone, so the same
        instant round-trips as a different ISO string than the one first
        written. Normalising here keeps datePublished byte-stable across
        republishes instead of appearing to change every time.
        """
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    document = {
        "schema_version": CONTENT_SCHEMA_VERSION,
        "id": article_id,
        "slug": slug,
        "title": title,
        "meta_title": meta_title or title,
        "meta_description": meta_description or "",
        "primary_keyword": primary_keyword,
        "html": html,
        # Kept separate from the body so the site can render the visible FAQ
        # accordion and the FAQPage schema from one source, which is what stops
        # the two drifting apart into a cloaking penalty.
        "faqs": [
            {"question": f.get("question") or "", "answer": f.get("answer") or ""}
            for f in faqs if (f.get("question") or "").strip()
        ],
        "featured_image": image_relative,
        "featured_image_alt": featured_image_alt or "",
        "author": author,
        "from_author_story": from_author_story or "",
        "published_at": as_utc(published_at or now),
        "updated_at": as_utc(now),
        # Drafts are written so they can be previewed, but the site excludes
        # them from the index and the sitemap and marks them noindex.
        "is_draft": is_draft,
    }
    # Additive fields (blog engine: content_format). Never overrides the keys
    # above, so the site's contract stays exactly what it was.
    for key, value in (extra or {}).items():
        document.setdefault(key, value)

    payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    path = os.path.join(settings.SITE_CONTENT_DIR, f"{slug}.json")
    _write_atomic(path, payload)

    return PublishedArticle(
        slug=slug,
        url=f"{settings.SITE_BLOG_BASE_URL.rstrip('/')}/{slug}",
        path=path,
        image_path=image_relative,
        bytes_written=len(payload),
    )


def unpublish(slug: str) -> bool:
    """Withdraw an article. Returns whether anything was removed."""
    removed = False

    path = os.path.join(settings.SITE_CONTENT_DIR, f"{slug}.json")
    if os.path.isfile(path):
        try:
            os.remove(path)
            removed = True
        except OSError as exc:
            raise ServiceUnavailable(
                "publisher", f"could not remove {path} ({exc.strerror})")

    for extension in (".png", ".jpg", ".webp"):
        image = os.path.join(settings.SITE_MEDIA_DIR, f"{slug}{extension}")
        if os.path.isfile(image):
            try:
                os.remove(image)
            except OSError:
                pass

    return removed


def is_published(slug: str) -> bool:
    return os.path.isfile(os.path.join(settings.SITE_CONTENT_DIR, f"{slug}.json"))


def published_slugs() -> List[str]:
    directory = settings.SITE_CONTENT_DIR
    if not os.path.isdir(directory):
        return []
    return sorted(name[:-5] for name in os.listdir(directory)
                  if name.endswith(".json"))


# ---------------------------------------------------------------------------
# Blog Visual Engine outputs
# ---------------------------------------------------------------------------
def publish_page(slug: str, html: str) -> str:
    """Write the pre-rendered article page the site serves as a file."""
    directory = os.path.join(settings.SITE_CONTENT_DIR, slug)
    _ensure_dir(directory)
    path = os.path.join(directory, "index.html")
    _write_atomic(path, html.encode("utf-8"))
    return path


def unpublish_page(slug: str) -> bool:
    path = os.path.join(settings.SITE_CONTENT_DIR, slug, "index.html")
    if not os.path.isfile(path):
        return False
    os.unlink(path)
    try:
        os.rmdir(os.path.dirname(path))
    except OSError:
        pass
    return True


def publish_engine_css() -> str:
    """Write the content-hashed deferred stylesheet. Idempotent: same content,
    same name, so republishing every article costs one write of one file."""
    from app.blog_engine import css
    directory = os.path.join(settings.SITE_MEDIA_DIR, "engine")
    _ensure_dir(directory)
    path = os.path.join(directory, css.deferred_filename())
    if not os.path.isfile(path):
        _write_atomic(path, css.build_deferred().encode("utf-8"))
    return path
