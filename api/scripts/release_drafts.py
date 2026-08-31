"""Release articles that were published while the go-live gate was closed.

An article published during a lapsed approval was written to disk with
"is_draft": true. The site honours that flag by hiding it from the blog index
and the sitemap, so the article exists at its URL but nothing links to it and
Google is never told. Turning the gate off fixes new publishes; it does not
rewrite files already on disk. This does.

It rewrites the flag in place, leaves every other field untouched, and then
tells IndexNow about the URLs it released.

Usage:
    python -m scripts.release_drafts --dry-run     # list what would change
    python -m scripts.release_drafts               # release them
    python -m scripts.release_drafts --no-indexnow # release, skip the ping
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.seo.services import indexnow  # noqa: E402

SITE_URL = "https://agenticaiautomation.co"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would change without writing")
    parser.add_argument("--no-indexnow", action="store_true",
                        help="release the drafts but do not submit the URLs")
    parser.add_argument("--dir", default=settings.SITE_CONTENT_DIR,
                        help="published article directory")
    args = parser.parse_args()

    directory = args.dir
    if not os.path.isdir(directory):
        print(f"ERROR: {directory} is not a directory.", file=sys.stderr)
        return 1

    released, skipped, failed = [], [], []

    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                document = json.load(fh)
        except (OSError, ValueError) as exc:
            failed.append((name, str(exc)))
            continue

        if not document.get("is_draft"):
            skipped.append(name)
            continue

        slug = document.get("slug") or name[:-5]
        if args.dry_run:
            released.append(slug)
            continue

        document["is_draft"] = False

        # Same write discipline the publisher uses: a full temp file replaced
        # atomically, so a reader never sees a half-written article.
        temp_path = f"{path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as fh:
                json.dump(document, fh, ensure_ascii=False, indent=2)
            os.chmod(temp_path, 0o644)
            os.replace(temp_path, path)
        except OSError as exc:
            failed.append((name, str(exc)))
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            continue

        released.append(slug)

    verb = "would release" if args.dry_run else "released"
    print(f"{verb}: {len(released)}")
    for slug in released:
        print(f"  {SITE_URL}/blog/{slug}")
    print(f"already live: {len(skipped)}")
    if failed:
        print(f"failed: {len(failed)}", file=sys.stderr)
        for name, reason in failed:
            print(f"  {name}: {reason}", file=sys.stderr)

    if released and not args.dry_run and not args.no_indexnow:
        urls = [f"{SITE_URL}/blog/{slug}" for slug in released]
        # The blog index and sitemap now list these, so tell Google about those
        # two as well — they changed the moment the flag flipped.
        urls += [f"{SITE_URL}/blog", f"{SITE_URL}/sitemap-blog.xml"]
        result = indexnow.submit(urls)
        print(f"IndexNow: {result}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
