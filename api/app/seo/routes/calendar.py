"""12-week editorial calendar, including the 60-row CSV import."""
import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.models import User
from app.seo import enums
from app.seo.deps import admin_user, seo_user
from app.seo.matrix import approved_countries
from app.seo.models import SeoCalendar
from app.seo.schemas import CalendarImportResult, CalendarRowResponse

router = APIRouter(prefix="/api/seo/calendar", tags=["seo-calendar"])

# Accepted CSV headers, lowercased. Aliases keep Jai's spreadsheet from having
# to match the DB column names exactly.
COLUMN_ALIASES = {
    "week": "week_number", "week_number": "week_number", "week no": "week_number",
    "type": "article_type", "article_type": "article_type",
    "vertical": "vertical",
    "country": "country",
    "title": "title",
    "keyword": "primary_keyword", "primary_keyword": "primary_keyword",
    "kd": "kd", "difficulty": "kd", "keyword_difficulty": "kd",
    "volume": "volume", "search_volume": "volume", "monthly_search_volume": "volume",
    "intent": "buyer_intent", "buyer_intent": "buyer_intent",
    "brief": "brief", "notes": "brief",
}


@router.get("", response_model=List[CalendarRowResponse])
def list_calendar(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    week_number: Optional[int] = None,
    vertical: Optional[enums.Vertical] = None,
    limit: int = Query(default=200, le=1000),
):
    query = db.query(SeoCalendar)
    if week_number is not None:
        query = query.filter(SeoCalendar.week_number == week_number)
    if vertical is not None:
        query = query.filter(SeoCalendar.vertical == vertical.value)
    return (query.order_by(SeoCalendar.week_number.asc().nullslast(),
                           SeoCalendar.created_at.asc())
            .limit(limit).all())


@router.post("/import-csv", response_model=CalendarImportResult)
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    replace: bool = Query(default=False,
                          description="Delete unconverted rows before importing"),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    """Import the 60-row calendar. Rows are validated individually.

    A row that fails validation is reported and skipped; the rest still import,
    so a single typo does not reject the whole file.
    """
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    if replace:
        # Only drop rows that have not yet become articles.
        db.query(SeoCalendar).filter(SeoCalendar.article_id.is_(None)).delete()

    imported, skipped, errors = 0, 0, []
    valid_verticals = {e.value for e in enums.Vertical}
    valid_countries = {e.value for e in enums.Country}
    valid_types = {e.value for e in enums.ArticleType}
    valid_intents = {e.value for e in enums.BuyerIntent}

    for line_number, raw_row in enumerate(reader, start=2):
        row = {}
        for key, value in raw_row.items():
            if key is None:
                continue
            mapped = COLUMN_ALIASES.get(key.strip().lower())
            if mapped:
                row[mapped] = (value or "").strip()

        article_type = (row.get("article_type") or "").lower()
        vertical = (row.get("vertical") or "").lower().replace(" ", "_").replace("-", "_")
        country = (row.get("country") or "").lower() or None
        intent = (row.get("buyer_intent") or "").lower() or None

        problems = []
        if article_type not in valid_types:
            problems.append(f"article_type '{article_type}' must be one of "
                            f"{sorted(valid_types)}")
        if vertical not in valid_verticals:
            problems.append(f"vertical '{vertical}' must be one of {sorted(valid_verticals)}")
        if country and country not in valid_countries:
            problems.append(f"country '{country}' must be one of {sorted(valid_countries)}")
        if intent and intent not in valid_intents:
            problems.append(f"buyer_intent '{intent}' must be one of {sorted(valid_intents)}")

        if not problems:
            if article_type == enums.ArticleType.onpage.value:
                if not country:
                    problems.append("onpage rows require a country")
                elif country not in approved_countries(db, enums.Vertical(vertical)):
                    problems.append(
                        f"{country} is not an approved market for {vertical}; approved: "
                        f"{approved_countries(db, enums.Vertical(vertical))}")
            elif country:
                problems.append("content rows must not set a country")

        if problems:
            skipped += 1
            errors.append({"line": line_number, "problems": problems, "row": raw_row})
            continue

        db.add(SeoCalendar(
            week_number=_int_or_none(row.get("week_number")),
            article_type=article_type,
            vertical=vertical,
            country=country,
            title=row.get("title") or None,
            primary_keyword=row.get("primary_keyword") or None,
            kd=_int_or_none(row.get("kd")),
            volume=_int_or_none(row.get("volume")),
            buyer_intent=intent,
            brief_json={"brief": row.get("brief")} if row.get("brief") else None,
        ))
        imported += 1

    log_event(db, "seo.calendar.imported", current_user, request,
              target_type="seo_calendar",
              detail=f"{imported} imported, {skipped} skipped", commit=False)
    db.commit()
    return CalendarImportResult(imported=imported, skipped=skipped, errors=errors)


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        return None
