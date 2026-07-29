"""MinIO object storage for featured images.

Falls back to a local directory when MinIO is not configured, so image upload
and alt-caption generation still work on a box without the object store. The
stored path is opaque to callers — always read it back through `get_object`.
"""
import io
import os
import uuid
from typing import Optional, Tuple

from app.config import settings
from app.seo.services import ServiceUnavailable

LOCAL_FALLBACK_DIR = "/var/www/agenticai-dashboard/uploads/seo-images"

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_BYTES = 10 * 1024 * 1024


def _minio_configured() -> bool:
    return bool(settings.MINIO_ENDPOINT and settings.MINIO_ACCESS_KEY
                and settings.MINIO_SECRET_KEY)


def _minio_client():
    try:
        from minio import Minio
    except ImportError:
        raise ServiceUnavailable("minio", "the `minio` package is not installed")
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def validate_image(content: bytes, mime_type: str) -> None:
    if mime_type not in ALLOWED_MIME:
        raise ServiceUnavailable(
            "storage",
            f"unsupported image type {mime_type}. Allowed: "
            f"{', '.join(sorted(ALLOWED_MIME))}.",
        )
    if len(content) > MAX_BYTES:
        raise ServiceUnavailable(
            "storage", f"image is {len(content) // 1024}KB; the limit is 10MB.")
    if not content:
        raise ServiceUnavailable("storage", "the uploaded file is empty")


def put_object(article_id: str, content: bytes, mime_type: str) -> str:
    """Store the image and return the path recorded on the article."""
    validate_image(content, mime_type)
    extension = ALLOWED_MIME[mime_type]
    # article_id is a server-generated UUID, so it cannot contain path separators.
    key = f"{article_id}/{uuid.uuid4().hex}{extension}"

    if _minio_configured():
        client = _minio_client()
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
        client.put_object(
            settings.MINIO_BUCKET, key, io.BytesIO(content), len(content),
            content_type=mime_type,
        )
        return f"minio://{settings.MINIO_BUCKET}/{key}"

    destination = os.path.join(LOCAL_FALLBACK_DIR, key)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "wb") as fh:
        fh.write(content)
    return f"file://{destination}"


def get_object(path: str) -> Tuple[bytes, str]:
    """Read an image back. Returns (bytes, mime_type)."""
    if path.startswith("minio://"):
        _, _, remainder = path.partition("minio://")
        bucket, _, key = remainder.partition("/")
        client = _minio_client()
        response = None
        try:
            response = client.get_object(bucket, key)
            content = response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()
    elif path.startswith("file://"):
        local = path[len("file://"):]
        # Confine reads to the upload directory even though paths are server-generated.
        resolved = os.path.realpath(local)
        if not resolved.startswith(os.path.realpath(LOCAL_FALLBACK_DIR) + os.sep):
            raise ServiceUnavailable("storage", "image path is outside the upload directory")
        with open(resolved, "rb") as fh:
            content = fh.read()
    else:
        raise ServiceUnavailable("storage", f"unrecognised image path: {path}")

    extension = os.path.splitext(path)[1].lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(extension, "image/jpeg")
    return content, mime


def filename_for(path: str) -> str:
    return os.path.basename(path) or "featured-image.jpg"
