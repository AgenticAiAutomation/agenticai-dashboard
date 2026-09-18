"""JSON-LD generated from blocks. Writers never hand-write structured data.

Everything here is built from the same RenderResult the page was rendered
from, so the markup and the visible page cannot disagree — marking up a
question that is not on the page is a cloaking penalty, and the only way to
be sure it never happens is to derive both from one source.
"""
from __future__ import annotations

from typing import Dict, List

from app.blog_engine.inline import text_of
from app.blog_engine.render import SITE_URL, ArticleMeta, RenderResult

ORG_ID = f"{SITE_URL}/#organization"
WEBSITE_ID = f"{SITE_URL}/#website"
LOGO = f"{SITE_URL}/static/images/logo-v2.png"


def _absolute(path: str) -> str:
    return path if path.startswith("http") else f"{SITE_URL}{path}"


def _author(meta: ArticleMeta) -> Dict:
    a = meta.author
    if a.kind == "Person":
        person: Dict = {"@type": "Person", "name": a.name}
        if a.url:
            person["url"] = a.url
        if a.job_title:
            person["jobTitle"] = a.job_title
        if a.same_as:
            person["sameAs"] = a.same_as
        if a.credentials:
            person["hasCredential"] = [
                {"@type": "EducationalOccupationalCredential", "name": c} for c in a.credentials]
        person["worksFor"] = {"@id": ORG_ID}
        return person
    return {"@type": "Organization", "@id": ORG_ID, "name": a.name}


def article(meta: ArticleMeta, result: RenderResult) -> Dict:
    canonical = meta.canonical
    doc: Dict = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "@id": f"{canonical}#article",
        "isPartOf": {"@id": WEBSITE_ID},
        "publisher": {"@type": "Organization", "@id": ORG_ID, "name": "Agentic AI Automation",
                      "logo": {"@type": "ImageObject", "url": LOGO}},
        "headline": meta.title,
        "description": meta.meta_description,
        "datePublished": meta.published_at,
        "dateModified": meta.updated_at or meta.published_at,
        "author": _author(meta),
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "wordCount": result.word_count,
        "inLanguage": "en-IN",
    }
    if meta.category:
        doc["articleSection"] = meta.category
    if meta.primary_keyword:
        doc["keywords"] = meta.primary_keyword
    images = []
    if meta.hero:
        images.append({"@type": "ImageObject", "url": _absolute(meta.hero.src),
                       "width": meta.hero.width, "height": meta.hero.height,
                       "caption": meta.hero.alt})
    for img in result.images[:3]:
        images.append({"@type": "ImageObject", "url": _absolute(img.src),
                       "width": img.width, "height": img.height, "caption": img.alt})
    if images:
        doc["image"] = images
    return doc


def breadcrumbs(meta: ArticleMeta) -> Dict:
    items = [("Home", SITE_URL + "/"), ("Blog", SITE_URL + "/blog")]
    if meta.category:
        items.append((meta.category, f"{SITE_URL}/blog?category={meta.category.lower().replace(' ', '-')}"))
    items.append((meta.title, meta.canonical))
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(items, start=1)
        ],
    }


def faq_page(result: RenderResult) -> Dict | None:
    if not result.faqs:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in result.faqs
        ],
    }


def how_tos(meta: ArticleMeta, result: RenderResult) -> List[Dict]:
    out = []
    for block in result.steps:
        if len(block.content) < 3:
            continue
        doc: Dict = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": block.attrs.title or meta.title,
            "step": [],
        }
        if block.attrs.total_time:
            doc["totalTime"] = block.attrs.total_time
        for i, step in enumerate(block.content, start=1):
            s: Dict = {"@type": "HowToStep", "position": i,
                       "name": text_of(step.title), "url": f"{meta.canonical}#{block.id}-s{i}"}
            if step.body:
                s["text"] = text_of(step.body)
            if step.image:
                s["image"] = _absolute(step.image.src)
            doc["step"].append(s)
        out.append(doc)
    return out


def videos(meta: ArticleMeta, result: RenderResult) -> List[Dict]:
    out = []
    for v in result.videos:
        a = v.attrs
        doc: Dict = {
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": a.title,
            "description": a.description,
            "thumbnailUrl": [_absolute(a.poster)],
            "uploadDate": a.upload_date,
            "duration": a.duration,
        }
        if a.kind == "youtube":
            doc["embedUrl"] = f"https://www.youtube-nocookie.com/embed/{a.youtube_id}"
        else:
            doc["contentUrl"] = _absolute(a.src or "")
        out.append(doc)
    return out


def quotations(result: RenderResult) -> List[Dict]:
    out = []
    for q in result.quotes:
        doc: Dict = {"@context": "https://schema.org", "@type": "Quotation",
                     "text": text_of(q.content),
                     "creator": {"@type": "Person", "name": q.attrs.attribution}}
        if q.attrs.company:
            doc["creator"]["affiliation"] = {"@type": "Organization", "name": q.attrs.company}
        if q.attrs.role:
            doc["creator"]["jobTitle"] = q.attrs.role
        out.append(doc)
    return out


def build(meta: ArticleMeta, result: RenderResult) -> List[Dict]:
    docs: List[Dict] = [article(meta, result), breadcrumbs(meta)]
    faq = faq_page(result)
    if faq:
        docs.append(faq)
    docs.extend(how_tos(meta, result))
    docs.extend(videos(meta, result))
    docs.extend(quotations(result))
    return docs
