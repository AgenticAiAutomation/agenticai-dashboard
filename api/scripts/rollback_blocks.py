"""Roll the Blog Visual Engine's database change back.

    python -m scripts.rollback_blocks --dry-run   # count what would be lost
    python -m scripts.rollback_blocks --confirm   # alembic downgrade 002

Drops content_blocks, content_format and seo_article_revisions — and only
those. The markdown columns are never touched, so every article still renders
through the legacy path afterwards. Block articles lose their block content:
the script refuses without --confirm and prints exactly how many articles
and revisions that is.

The flag is the first rollback, not this. Set BLOG_ENGINE_V2=false on the
API and the site, restart both, and the engine is inert with the data kept.
Use this only when the schema itself must go.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401,E402
from app.database import SessionLocal  # noqa: E402
from app.seo.models import SeoArticle, SeoArticleRevision  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    n_articles = db.query(SeoArticle).filter(SeoArticle.content_format == "blocks").count()
    n_revisions = db.query(SeoArticleRevision).count()
    print(f"block articles : {n_articles}  (their content_blocks will be dropped; markdown stays)")
    print(f"revisions      : {n_revisions}")
    if args.dry_run or not args.confirm:
        print("Nothing changed. Pass --confirm to run `alembic downgrade 002`.")
        return 0
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "002"], cwd=api_dir)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
