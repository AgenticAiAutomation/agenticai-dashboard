"""Render the Phase 1 fixture to a content directory the marketing site can serve.

    python -m scripts.render_fixture --out /path/to/published

Writes:
    <out>/articles/<slug>/index.html      the page, served as a file
    <out>/media/engine/blog-engine.<hash>.css  the deferred stylesheet
    <out>/media/engine-demo/*.jpg          placeholder images for the fixture

and prints the validator report and the size budget. Nothing here touches a
database or the network.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blog_engine import css, validate  # noqa: E402
from app.blog_engine.render import ArticleMeta, Author, render_page  # noqa: E402
from app.blog_engine.schema import ImageAttrs, parse_blocks  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "app", "blog_engine", "fixtures", "sample-article.json")


def load_fixture(path: str = FIXTURE):
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    m = doc["meta"]
    hero = ImageAttrs.model_validate(m["hero"]) if m.get("hero") else None
    meta = ArticleMeta(
        slug=m["slug"], title=m["title"], meta_title=m.get("meta_title"),
        meta_description=m.get("meta_description", ""),
        published_at=m["published_at"], updated_at=m.get("updated_at", m["published_at"]),
        category=m.get("category"), primary_keyword=m.get("primary_keyword"),
        hero=hero, related=[tuple(r) for r in m.get("related", [])],
        from_author_story=m.get("from_author_story"),
        author=Author(**m["author"]) if m.get("author") else ArticleMeta.__dataclass_fields__["author"].default_factory(),
    )
    return meta, parse_blocks(doc["blocks"])


def placeholder_images(media_dir: str, paths) -> int:
    """Generate labelled JPEGs so the demo has real, correctly-sized images."""
    from PIL import Image, ImageDraw
    made = 0
    for src in sorted(set(paths)):
        if not src.startswith("/static/blog/"):
            continue
        rel = src[len("/static/blog/"):]
        target = os.path.join(media_dir, rel)
        if os.path.exists(target):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        w, h = (1600, 900) if "scan" not in rel else (1200, 900)
        img = Image.new("RGB", (w, h), (21, 18, 14))
        d = ImageDraw.Draw(img)
        for y in range(0, h, 60):
            d.line([(0, y), (w, y)], fill=(29, 25, 19), width=1)
        d.rectangle([40, 40, w - 40, h - 40], outline=(255, 90, 0), width=6)
        d.text((80, 80), os.path.basename(rel), fill=(250, 247, 241))
        d.text((80, 120), f"{w}x{h} placeholder", fill=(169, 157, 137))
        img.save(target, "JPEG", quality=72, optimize=True)
        made += 1
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="published directory (articles/ and media/ go under it)")
    ap.add_argument("--fixture", default=FIXTURE)
    ap.add_argument("--no-analytics", action="store_true")
    args = ap.parse_args()

    meta, blocks = load_fixture(args.fixture)
    t0 = time.perf_counter()
    html, result = render_page(blocks, meta, analytics=not args.no_analytics)
    ms = (time.perf_counter() - t0) * 1000

    art_dir = os.path.join(args.out, "articles", meta.slug)
    os.makedirs(art_dir, exist_ok=True)
    with open(os.path.join(art_dir, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)

    eng_dir = os.path.join(args.out, "media", "engine")
    os.makedirs(eng_dir, exist_ok=True)
    with open(os.path.join(eng_dir, css.deferred_filename()), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(css.build_deferred())

    made = placeholder_images(os.path.join(args.out, "media"),
                              result.assets + ([meta.hero.src] if meta.hero else []))

    violations = validate.validate_article(blocks, meta, result)

    print(f"rendered      : {meta.slug}")
    print(f"blocks        : {len(blocks)} ({len(set(result.block_types))} distinct types)")
    print(f"words         : {result.word_count}  (~{result.reading_minutes} min)  visuals: {result.visuals}")
    print(f"headings      : {len(result.headings)}   faqs: {len(result.faqs)}   images: {len(result.images)}   videos: {len(result.videos)}")
    print(f"render time   : {ms:.1f} ms")
    print(f"page          : {len(html.encode('utf-8')) / 1024:.1f} KB raw -> {art_dir}\\index.html")
    print(f"critical css  : {css.critical_size_bytes() / 1024:.1f} KB inline (budget 14 KB)")
    print(f"deferred css  : {len(css.build_deferred().encode()) / 1024:.1f} KB -> media/engine/{css.deferred_filename()}")
    print(f"placeholders  : {made} images generated")
    print(f"validators    : {len(validate.blocking(violations))} blocking, "
          f"{len(violations) - len(validate.blocking(violations))} warnings")
    for v in violations:
        print(f"   {v}")
    return 1 if validate.blocking(violations) else 0


if __name__ == "__main__":
    raise SystemExit(main())
