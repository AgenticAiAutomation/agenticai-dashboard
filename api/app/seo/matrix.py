"""Approved country x vertical matrix.

    WhatsApp Automation -> India only
    RPA                 -> NZ, Ireland, UK
    n8n                 -> NZ, Ireland, UK, India
    Agentic AI          -> India, NZ, Ireland, UK

The authoritative copy lives in seo_country_vertical_matrix (seeded by the
migration) so it can be changed without a redeploy. APPROVED_MATRIX below is
the seed and the fallback used when the table has not been populated yet.
"""
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.seo.enums import ArticleType, Country, Vertical

APPROVED_MATRIX = {
    Vertical.whatsapp: [Country.india],
    Vertical.rpa: [Country.nz, Country.ireland, Country.uk],
    Vertical.n8n: [Country.nz, Country.ireland, Country.uk, Country.india],
    Vertical.agentic_ai: [Country.india, Country.nz, Country.ireland, Country.uk],
}

VERTICAL_LABELS = {
    Vertical.whatsapp: "WhatsApp Automation",
    Vertical.rpa: "RPA",
    Vertical.n8n: "n8n",
    Vertical.agentic_ai: "Agentic AI",
}

COUNTRY_LABELS = {
    Country.india: "India",
    Country.nz: "New Zealand",
    Country.ireland: "Ireland",
    Country.uk: "United Kingdom",
}


def approved_countries(db: Session, vertical: Vertical) -> List[str]:
    """Countries approved for a vertical, read from the DB with a code fallback."""
    from app.seo.models import CountryVerticalMatrix

    rows = (
        db.query(CountryVerticalMatrix)
        .filter(
            CountryVerticalMatrix.vertical == vertical.value,
            CountryVerticalMatrix.approved.is_(True),
        )
        .all()
    )
    if rows:
        return [r.country for r in rows]
    return [c.value for c in APPROVED_MATRIX.get(vertical, [])]


def is_approved(db: Session, vertical: Vertical, country: Country) -> bool:
    return country.value in approved_countries(db, vertical)


def validate_country_vertical(
    db: Session,
    article_type: ArticleType,
    vertical: Vertical,
    country: Optional[Country],
) -> None:
    """Enforcement rule 1. Raises 422 with an actionable message.

    Content articles carry no country lock; supplying one is rejected rather
    than silently dropped, so the caller finds out their form is wrong.
    """
    if article_type == ArticleType.content:
        if country is not None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "country_not_allowed_for_content",
                    "message": (
                        "Article type 'content' has no country lock. "
                        "Leave country empty, or switch the type to 'onpage'."
                    ),
                },
            )
        return

    if country is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "country_required",
                "message": (
                    f"Article type 'onpage' requires a country. Approved countries for "
                    f"{VERTICAL_LABELS.get(vertical, vertical.value)}: "
                    f"{', '.join(approved_countries(db, vertical)) or 'none'}."
                ),
                "vertical": vertical.value,
                "approved_countries": approved_countries(db, vertical),
            },
        )

    allowed = approved_countries(db, vertical)
    if country.value not in allowed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "country_vertical_not_approved",
                "message": (
                    f"{COUNTRY_LABELS.get(country, country.value)} is not an approved market for "
                    f"{VERTICAL_LABELS.get(vertical, vertical.value)}. "
                    f"Approved: {', '.join(allowed) or 'none'}."
                ),
                "vertical": vertical.value,
                "country": country.value,
                "approved_countries": allowed,
            },
        )


def seed_rows() -> List[dict]:
    """Full cross product with an approved flag, for the migration seed."""
    rows = []
    for vertical in Vertical:
        allowed = APPROVED_MATRIX.get(vertical, [])
        for country in Country:
            rows.append(
                {
                    "vertical": vertical.value,
                    "country": country.value,
                    "approved": country in allowed,
                }
            )
    return rows
