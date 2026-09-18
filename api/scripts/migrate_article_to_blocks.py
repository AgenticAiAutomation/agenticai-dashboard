"""Convert ONE legacy article to blocks. Dry run by default.

    python -m scripts.migrate_article_to_blocks <slug-or-id>            # show what would change
    python -m scripts.migrate_article_to_blocks <slug-or-id> --apply    # write content_blocks

No bulk mode on purpose (work order 10.4): migrate one low-traffic article,
check it renders, check Search Console, then the next. The article's
markdown columns are never modified; --apply sets content_blocks and
content_format='blocks' and writes revision 1. Publishing is a separate,
deliberate step in the dashboard.

Anything the converter cannot map with confidence lands in a single
legacy_html block and is listed under NOTES for a human to split in the
editor.
"""
import argparse
import difflib
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401,E402
from app.blog_engine import convert, validate  # noqa: E402
from app.blog_engine.render import ArticleMeta, render_article  # noqa: E402
from app.blog_engine.schema import parse_blocks  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seo.models import SeoArticle, SeoArticleFaq, SeoArticleRevision  # noqa: E402


def image_dims(src: str):
    """Dimensions of an image already in the published media dir, else None."""
    if not src.startswith("/static/blog/"):
        return None
    path = os.path.join(settings.SITE_MEDIA_DIR, src[len("/static/blog/"):])
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("article", help="slug or UUID")
    ap.add_argument("--apply", action="store_true", help="write the blocks (default: dry run)")
    args = ap.parse_args()

    db = SessionLocal()
    q = db.query(SeoArticle)
    try:
        article = q.filter(SeoArticle.id == uuid.UUID(args.article)).first()
    except ValueError:
        article = q.filter(SeoArticle.slug == args.article).first()
    if article is None:
        print(f"no article matches {args.article!r}", file=sys.stderr)
        return 1
    if article.content_format == "blocks":
        print(f"{article.slug}: already blocks ({len(article.content_blocks or [])} blocks). Nothing to do.")
        return 0

    md = article.final_md or article.team_edit_md or article.author_draft_md or ""
    faqs = [(f.question, f.answer or "") for f in
            db.query(SeoArticleFaq).filter(SeoArticleFaq.article_id == article.id)
            .order_by(SeoArticleFaq.position_in_article).all()]
    blocks, notes = convert.markdown_to_blocks(md, faqs, image_dims)
    parsed = parse_blocks(blocks)
    result = render_article(parsed)
    meta = ArticleMeta(slug=article.slug or "untitled", title=article.title or "",
                       meta_title=article.meta_title, meta_description=article.meta_description or "")
    violations = validate.validate_article(parsed, meta, result)

    print(f"article : {article.slug}  ({article.status})")
    print(f"source  : {len(md.split())} words of markdown, {len(faqs)} FAQs")
    print(f"result  : {len(blocks)} blocks -> {result.word_count} words, {result.visuals} visuals")
    from collections import Counter
    print(f"types   : {dict(Counter(b['type'] for b in blocks))}")
    if notes:
        print("NOTES (need a human):")
        for n in notes:
            print(f"   - {n}")
    blocking = validate.blocking(violations)
    print(f"validators: {len(blocking)} blocking, {len(violations) - len(blocking)} warnings")
    for v in violations[:12]:
        print(f"   {v}")

    # Text diff: the markdown as written vs the projection of the blocks, so a
    # dropped sentence is visible before anything is applied.
    projection = convert.blocks_to_markdown(parsed)
    diff = list(difflib.unified_diff(md.splitlines(), projection.splitlines(),
                                     "markdown (source)", "blocks (projection)", lineterm="", n=1))
    changed = [l for l in diff[2:] if l.startswith(("+", "-")) and l.strip("+- ")]
    print(f"diff    : {len(changed)} changed lines between the source and the projection")
    for l in diff[:60]:
        print("   " + l)
    if len(diff) > 60:
        print(f"   ... {len(diff) - 60} more lines")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to convert.")
        return 0

    article.content_blocks = blocks
    article.content_format = "blocks"
    db.add(SeoArticleRevision(article_id=article.id, revision_number=1, content_blocks=blocks,
                              meta={"title": article.title, "slug": article.slug,
                                    "meta_title": article.meta_title,
                                    "meta_description": article.meta_description,
                                    "primary_keyword": article.primary_keyword},
                              note="migrated from markdown"))
    db.commit()
    print(f"\nAPPLIED: {article.slug} is now content_format=blocks (revision 1). "
          "Open it in the block editor, fix the NOTES, then publish from the dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
