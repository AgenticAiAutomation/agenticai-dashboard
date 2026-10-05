"""Score parity check for the Blog Playbook deploy (§1 and §6.1 of the brief).

Scores every article in the database with the house engine and Rank Math,
exactly as the score route does, and writes the totals to a JSON file. Run it
before the deploy and again after; --compare must report no differences.

Read-only: it never writes a score row and never changes an article. The
paid AI-detection check is skipped (see snapshot()); the image-size read and
the local LanguageTool call happen exactly as in the score route.

Usage, always from the api/ directory. Before the deploy the script is not in
the checkout yet, so copy it to /root and run that copy:
    python /root/playbook_score_parity.py --out /root/parity-before.json
    python -m scripts.playbook_score_parity --out /root/parity-after.json
    python -m scripts.playbook_score_parity --compare /root/parity-before.json /root/parity-after.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The "before" snapshot runs from a copy in /root against the code that is
# checked out at the time, so the current directory (api/) wins.
sys.path.insert(0, os.getcwd())


def snapshot(path: str) -> int:
    from app.config import settings
    # The AI-detection check is a paid call with a noisy reading, so it would
    # spend money and differ run to run. It is switched off in this process
    # only (the check reports "skipped" in both snapshots); every other check,
    # including LanguageTool on the box, runs exactly as in the score route.
    settings.AI_DETECTION_PROVIDER = None

    from app.database import SessionLocal
    from app.seo.models import SeoArticle
    from app.seo.routes.articles import _build_context
    from app.seo.services import rankmath, scoring

    db = SessionLocal()
    results = {}
    try:
        for article in db.query(SeoArticle).order_by(SeoArticle.created_at).all():
            ctx = _build_context(db, article)
            house = scoring.score_article(ctx)
            rank = rankmath.score_article(rankmath.RankMathContext(
                markdown=ctx.markdown,
                primary_keyword=ctx.primary_keyword,
                title=ctx.meta_title or ctx.title,
                slug=ctx.slug,
                meta_description=ctx.meta_description,
                has_featured_image=bool(article.featured_image_path),
                featured_image_alt=ctx.featured_image_alt,
            ))
            results[str(article.id)] = {
                "slug": article.slug,
                "house_total": house["total_score"],
                "house_parameters": {p["key"]: p["points_earned"]
                                     for p in house["parameters"]},
                "rank_math_total": rank.get("total_score"),
            }
    finally:
        db.rollback()   # nothing was written; make that explicit
        db.close()

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=1, sort_keys=True)
    print(f"scored {len(results)} articles -> {path}")
    return 0


def compare(before_path: str, after_path: str) -> int:
    with open(before_path, encoding="utf-8") as handle:
        before = json.load(handle)
    with open(after_path, encoding="utf-8") as handle:
        after = json.load(handle)

    problems = []
    for article_id, old in before.items():
        new = after.get(article_id)
        if new is None:
            problems.append(f"{old['slug']}: missing after the deploy")
        elif new != old:
            problems.append(f"{old['slug']}: house {old['house_total']} -> "
                            f"{new['house_total']}, Rank Math {old['rank_math_total']} -> "
                            f"{new['rank_math_total']}")
    for article_id in after.keys() - before.keys():
        print(f"note: {after[article_id]['slug']} is new since the first snapshot")

    if problems:
        print("SCORE PARITY FAILED")
        for line in problems:
            print("  " + line)
        return 1
    print(f"SCORE PARITY OK — {len(before)} articles identical to the decimal")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="write a snapshot to this file")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    if args.compare:
        return compare(*args.compare)
    if args.out:
        return snapshot(args.out)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
