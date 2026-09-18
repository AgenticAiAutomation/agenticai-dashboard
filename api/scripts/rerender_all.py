"""Re-render every published block article.

    python -m scripts.rerender_all            # do it
    python -m scripts.rerender_all --dry-run  # list only

Run after anything that changes the rendered page without changing content:
the site's header/footer, design_tokens.json, a renderer fix. Each article's
index.html and JSON record are rewritten in place (atomic), the deferred
stylesheet is re-published under its new hash, and IndexNow is told about
the URLs. Takes seconds; the site picks up the files on the next request.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401,E402
from app.blog_engine.render import render_page  # noqa: E402
from app.blog_engine.routes import _meta  # noqa: E402
from app.blog_engine.schema import BlockError, parse_blocks  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seo import enums as seo_enums  # noqa: E402
from app.seo.models import SeoArticle  # noqa: E402
from app.seo.services import indexnow, publisher  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-indexnow", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    rows = (db.query(SeoArticle)
            .filter(SeoArticle.content_format == "blocks",
                    SeoArticle.status == seo_enums.ArticleStatus.published.value)
            .order_by(SeoArticle.published_at).all())
    print(f"{len(rows)} published block article(s)")
    done, failed, urls = [], [], []
    t0 = time.perf_counter()
    for article in rows:
        try:
            blocks = parse_blocks(article.content_blocks or [])
        except BlockError as exc:
            failed.append((article.slug, str(exc)))
            continue
        meta = _meta(db, article)
        meta.is_draft = False
        if args.dry_run:
            done.append(article.slug)
            continue
        html, result = render_page(blocks, meta)
        publisher.publish_page(article.slug, html)
        publisher.publish(
            article_id=str(article.id), slug=article.slug,
            title=article.title or article.primary_keyword, html=result.body_html,
            meta_title=article.meta_title, meta_description=article.meta_description,
            primary_keyword=article.primary_keyword,
            faqs=[{"question": q, "answer": a} for q, a in result.faqs],
            featured_image_path=article.featured_image_path,
            featured_image_alt=article.featured_image_alt, author=settings.BLOG_AUTHOR_NAME,
            from_author_story=article.from_author_story, published_at=article.published_at,
            is_draft=False, extra={"content_format": "blocks"})
        done.append(article.slug)
        urls.append(f"{settings.SITE_BLOG_BASE_URL.rstrip('/')}/{article.slug}")
    if not args.dry_run and done:
        publisher.publish_engine_css()
    ms = (time.perf_counter() - t0) * 1000
    verb = "would re-render" if args.dry_run else "re-rendered"
    print(f"{verb}: {len(done)} in {ms:.0f} ms")
    for s in done:
        print(f"  {s}")
    for s, why in failed:
        print(f"  FAILED {s}: {why}", file=sys.stderr)
    if urls and not args.no_indexnow and indexnow.configured():
        print("IndexNow:", indexnow.submit(urls))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
