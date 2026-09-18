"""Block schema.

Every block is an envelope {id, type, version, attrs, content}. Inline text is
a list of runs, each carrying marks ({"type": "bold"}, {"type": "link", ...}),
never HTML. Colours and sizes are token names — writers pick highlight.amber,
never #F59E0B — which is what keeps sixty articles looking like one site.

The union is discriminated on `type`, so a malformed block fails naming the
block id and the offending field rather than "invalid content".
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      field_validator, model_validator)

BLOCK_ID = re.compile(r"^blk_[A-Za-z0-9]{4,24}$")
ISO_DURATION = re.compile(r"^PT(?:\d+H)?(?:\d+M)?(?:\d+S)?$")

HIGHLIGHT_TOKENS = ("amber", "mint", "sky", "rose")
EMPHASIS_TOKENS = ("brand", "accent", "positive", "warning")


class BlockError(ValueError):
    """Raised by parse_blocks with a message that names the block and field."""


# ---------------------------------------------------------------------------
# Inline model
# ---------------------------------------------------------------------------
class Mark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["bold", "italic", "underline", "strike", "code", "link",
                  "highlight", "emphasis", "sup", "sub"]
    attrs: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_attrs(self) -> "Mark":
        if self.type == "link":
            href = self.attrs.get("href")
            if not isinstance(href, str) or not href.strip():
                raise ValueError("link mark needs attrs.href")
            if not re.match(r"^(https?://|/|#|mailto:)", href):
                raise ValueError(
                    f"link href must be http(s), site-relative, #anchor or mailto: — got {href!r}")
            extra = set(self.attrs) - {"href", "rel", "target", "title"}
            if extra:
                raise ValueError(f"link mark has unknown attrs {sorted(extra)}")
        elif self.type == "highlight":
            if self.attrs.get("token") not in HIGHLIGHT_TOKENS:
                raise ValueError(f"highlight token must be one of {HIGHLIGHT_TOKENS}")
        elif self.type == "emphasis":
            if self.attrs.get("token") not in EMPHASIS_TOKENS:
                raise ValueError(f"emphasis token must be one of {EMPHASIS_TOKENS}")
        elif self.attrs:
            raise ValueError(f"{self.type} mark takes no attrs")
        return self


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    marks: List[Mark] = Field(default_factory=list)


RichText = List[Run]


def _rich(value: Any, where: str) -> RichText:
    """Accept a list of runs, a single run, or a bare string."""
    if isinstance(value, str):
        return [Run(text=value)]
    if isinstance(value, dict):
        return [Run.model_validate(value)]
    if isinstance(value, list):
        return [Run.model_validate(v) if isinstance(v, dict) else Run(text=str(v)) for v in value]
    raise ValueError(f"{where}: expected text, a run, or a list of runs")


def plain_text(runs: RichText) -> str:
    return "".join(r.text for r in runs)


# ---------------------------------------------------------------------------
# Shared attribute models
# ---------------------------------------------------------------------------
class ImageVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    src: str
    width: int = Field(gt=0)
    format: Optional[Literal["avif", "webp", "jpeg", "png"]] = None


class ImageAttrs(BaseModel):
    """A figure. `src` is the fallback; `variants` become <picture> sources."""
    model_config = ConfigDict(extra="forbid")
    asset_id: Optional[str] = None
    src: str
    alt: str
    caption: Optional[str] = None
    credit: Optional[str] = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    layout: Literal["inset", "full", "breakout"] = "inset"
    priority: bool = False
    link: Optional[str] = None
    variants: List[ImageVariant] = Field(default_factory=list)
    lqip: Optional[str] = None  # data: URI, < 1KB, inline blur placeholder

    @field_validator("alt")
    @classmethod
    def _alt_rules(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("alt text is required")
        if len(v) > 125:
            raise ValueError(f"alt text is {len(v)} chars; keep it to 125")
        return v

    @field_validator("src")
    @classmethod
    def _src(cls, v: str) -> str:
        if not re.match(r"^(https?://|/)", v):
            raise ValueError("image src must be http(s) or site-relative")
        return v

    @model_validator(mode="after")
    def _alt_not_filename(self) -> "ImageAttrs":
        stem = re.sub(r"\.[a-z0-9]+$", "", self.src.rsplit("/", 1)[-1].lower())
        if self.alt.lower().replace(" ", "-") == stem or self.alt.lower() == stem:
            raise ValueError("alt text must describe the image, not repeat the filename")
        if self.lqip and (not self.lqip.startswith("data:image/") or len(self.lqip) > 1400):
            raise ValueError("lqip must be a data:image/ URI under ~1KB")
        if self.link and not re.match(r"^(https?://|/)", self.link):
            raise ValueError("image link must be http(s) or site-relative")
        return self


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------
class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = 1

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not BLOCK_ID.match(v):
            raise ValueError("block id must look like blk_XXXX (4-24 alphanumerics)")
        return v


class ParagraphAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant: Literal["normal", "lead"] = "normal"


class Paragraph(_Base):
    type: Literal["paragraph"]
    attrs: ParagraphAttrs = Field(default_factory=ParagraphAttrs)
    content: RichText

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "paragraph.content")


class HeadingAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal[2, 3, 4]
    gradient: bool = False
    id: Optional[str] = None  # explicit anchor; otherwise slugged from text


class Heading(_Base):
    type: Literal["heading"]
    attrs: HeadingAttrs
    content: RichText

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "heading.content")

    @model_validator(mode="after")
    def _rules(self) -> "Heading":
        if not plain_text(self.content).strip():
            raise ValueError("heading text is empty")
        if self.attrs.gradient and self.attrs.level != 2:
            raise ValueError("gradient headline is allowed on h2 only")
        return self


class KeyTakeawaysAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = "Key takeaways"


class KeyTakeaways(_Base):
    type: Literal["key_takeaways"]
    attrs: KeyTakeawaysAttrs = Field(default_factory=KeyTakeawaysAttrs)
    content: List[RichText]

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> List[RichText]:
        if not isinstance(v, list):
            raise ValueError("key_takeaways.content must be a list of items")
        return [_rich(item, "key_takeaways item") for item in v]

    @model_validator(mode="after")
    def _count(self) -> "KeyTakeaways":
        if not 3 <= len(self.content) <= 5:
            raise ValueError(f"key_takeaways needs 3-5 bullets, has {len(self.content)}")
        return self


class ListAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: Literal["bullet", "numbered", "checklist"] = "bullet"


class ListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: RichText
    checked: bool = False

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "list item")


class ListBlock(_Base):
    type: Literal["list"]
    attrs: ListAttrs = Field(default_factory=ListAttrs)
    content: List[ListItem]

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> List[Any]:
        if not isinstance(v, list) or not v:
            raise ValueError("list.content must be a non-empty list")
        return [x if isinstance(x, dict) and "content" in x else {"content": x} for x in v]


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: RichText
    body: RichText = Field(default_factory=list)
    image: Optional[ImageAttrs] = None

    @field_validator("title", "body", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "step")


class StepsAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    total_time: Optional[str] = None  # ISO 8601, e.g. PT20M, feeds HowTo

    @field_validator("total_time")
    @classmethod
    def _dur(cls, v: Optional[str]) -> Optional[str]:
        if v and not ISO_DURATION.match(v):
            raise ValueError("total_time must be an ISO 8601 duration like PT20M")
        return v


class Steps(_Base):
    type: Literal["steps"]
    attrs: StepsAttrs = Field(default_factory=StepsAttrs)
    content: List[Step]

    @model_validator(mode="after")
    def _count(self) -> "Steps":
        if len(self.content) < 2:
            raise ValueError("steps needs at least 2 steps")
        return self


class Image(_Base):
    type: Literal["image"]
    attrs: ImageAttrs
    content: List[Any] = Field(default_factory=list)


class GalleryAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: Literal["inset", "breakout"] = "breakout"
    caption: Optional[str] = None


class Gallery(_Base):
    type: Literal["gallery"]
    attrs: GalleryAttrs = Field(default_factory=GalleryAttrs)
    content: List[ImageAttrs]

    @model_validator(mode="after")
    def _count(self) -> "Gallery":
        if not 2 <= len(self.content) <= 4:
            raise ValueError(f"gallery takes 2-4 images, has {len(self.content)}")
        return self


class CompareSliderAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: ImageAttrs
    after: ImageAttrs
    label_before: str = "Before"
    label_after: str = "After"
    layout: Literal["inset", "breakout"] = "breakout"
    caption: Optional[str] = None


class CompareSlider(_Base):
    type: Literal["compare_slider"]
    attrs: CompareSliderAttrs
    content: List[Any] = Field(default_factory=list)


class VideoAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["file", "youtube"]
    src: Optional[str] = None          # file: mp4/webm path
    youtube_id: Optional[str] = None
    poster: str
    title: str
    description: str
    upload_date: str                   # YYYY-MM-DD
    duration: str                      # ISO 8601 PT1M30S
    width: int = 1280
    height: int = 720
    loop: bool = False                 # file: muted autoplay loop clip
    layout: Literal["inset", "breakout"] = "inset"
    caption: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self) -> "VideoAttrs":
        if self.kind == "file" and not (self.src and re.match(r"^(https?://|/)", self.src)):
            raise ValueError("file video needs a site-relative or http(s) src")
        if self.kind == "youtube" and not re.match(r"^[A-Za-z0-9_-]{11}$", self.youtube_id or ""):
            raise ValueError("youtube video needs an 11-character youtube_id")
        if not self.title.strip() or not self.description.strip():
            raise ValueError("video needs title and description (VideoObject requires both)")
        if not re.match(r"^(https?://|/)", self.poster):
            raise ValueError("video poster must be http(s) or site-relative")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", self.upload_date):
            raise ValueError("upload_date must be YYYY-MM-DD")
        if not ISO_DURATION.match(self.duration):
            raise ValueError("duration must be ISO 8601 like PT1M30S")
        return self


class Video(_Base):
    type: Literal["video"]
    attrs: VideoAttrs
    content: List[Any] = Field(default_factory=list)


class TableAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str
    has_header: bool = True
    align: List[Literal["left", "right", "center"]] = Field(default_factory=list)
    sortable: bool = False
    mobile: Literal["scroll", "stack"] = "scroll"
    layout: Literal["inset", "breakout"] = "inset"

    @field_validator("caption")
    @classmethod
    def _cap(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("every table needs a caption")
        return v.strip()


class Table(_Base):
    type: Literal["table"]
    attrs: TableAttrs
    content: List[List[RichText]]

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> List[List[RichText]]:
        if not isinstance(v, list) or not v:
            raise ValueError("table.content must be a non-empty list of rows")
        rows = []
        for r, row in enumerate(v):
            if not isinstance(row, list) or not row:
                raise ValueError(f"table row {r} must be a non-empty list of cells")
            rows.append([_rich(cell, f"table cell r{r}c{c}") for c, cell in enumerate(row)])
        return rows

    @model_validator(mode="after")
    def _rect(self) -> "Table":
        widths = {len(r) for r in self.content}
        if len(widths) != 1:
            raise ValueError(f"table rows have different lengths: {sorted(widths)}")
        cols = widths.pop()
        if self.attrs.align and len(self.attrs.align) != cols:
            raise ValueError(f"align has {len(self.attrs.align)} entries for {cols} columns")
        return self


class CalloutAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["info", "tip", "warning", "result"] = "info"
    title: Optional[str] = None


class Callout(_Base):
    type: Literal["callout"]
    attrs: CalloutAttrs = Field(default_factory=CalloutAttrs)
    content: RichText

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "callout.content")


class QuoteAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribution: str
    role: Optional[str] = None
    company: Optional[str] = None


class Quote(_Base):
    type: Literal["quote"]
    attrs: QuoteAttrs
    content: RichText

    @field_validator("content", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "quote.content")


class CodeAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str = "text"
    caption: Optional[str] = None

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9+#-]{1,20}$", v):
            raise ValueError("language must be a short lowercase label like python or json")
        return v


class Code(_Base):
    type: Literal["code"]
    attrs: CodeAttrs = Field(default_factory=CodeAttrs)
    content: str


class Stat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str            # shown as written, e.g. "1,240" or "62%"
    label: str
    numeric: Optional[float] = None   # enables count-up; None = static
    prefix: str = ""
    suffix: str = ""


class StatBand(_Base):
    type: Literal["stat_band"]
    attrs: Dict[str, Any] = Field(default_factory=dict)
    content: List[Stat]

    @model_validator(mode="after")
    def _count(self) -> "StatBand":
        if not 2 <= len(self.content) <= 4:
            raise ValueError(f"stat_band takes 2-4 numbers, has {len(self.content)}")
        return self


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    values: List[float]


class ChartAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["bar", "line", "donut"]
    title: str
    unit: str = ""
    labels: List[str]
    series: List[ChartSeries]
    layout: Literal["inset", "breakout"] = "inset"
    source: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self) -> "ChartAttrs":
        if not self.labels or not self.series:
            raise ValueError("chart needs labels and at least one series")
        for s in self.series:
            if len(s.values) != len(self.labels):
                raise ValueError(
                    f"series {s.name!r} has {len(s.values)} values for {len(self.labels)} labels")
        if self.kind == "donut" and len(self.series) != 1:
            raise ValueError("donut chart takes exactly one series")
        if len(self.series) > 4:
            raise ValueError("at most 4 series")
        return self


class Chart(_Base):
    type: Literal["chart"]
    attrs: ChartAttrs
    content: List[Any] = Field(default_factory=list)


class FlowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    sub: Optional[str] = None
    kind: Literal["system", "bot", "human", "decision", "result"] = "system"


class ProcessFlowAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    layout: Literal["inset", "breakout"] = "breakout"


class ProcessFlow(_Base):
    type: Literal["process_flow"]
    attrs: ProcessFlowAttrs = Field(default_factory=ProcessFlowAttrs)
    content: List[FlowNode]

    @model_validator(mode="after")
    def _count(self) -> "ProcessFlow":
        if not 2 <= len(self.content) <= 7:
            raise ValueError(f"process_flow takes 2-7 nodes, has {len(self.content)}")
        return self


class FaqItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    answer: RichText

    @field_validator("answer", mode="before")
    @classmethod
    def _c(cls, v: Any) -> RichText:
        return _rich(v, "faq answer")

    @field_validator("question")
    @classmethod
    def _q(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("faq question is empty")
        return v.strip()


class FaqAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = "Frequently asked questions"


class Faq(_Base):
    type: Literal["faq"]
    attrs: FaqAttrs = Field(default_factory=FaqAttrs)
    content: List[FaqItem]

    @model_validator(mode="after")
    def _count(self) -> "Faq":
        if not self.content:
            raise ValueError("faq needs at least one question")
        return self


class CtaAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str
    text: Optional[str] = None
    button_label: str
    href: str
    kind: Literal["service", "calendly", "contact"] = "service"

    @field_validator("href")
    @classmethod
    def _href(cls, v: str) -> str:
        if not re.match(r"^(https?://|/)", v):
            raise ValueError("cta href must be http(s) or site-relative")
        return v


class Cta(_Base):
    type: Literal["cta"]
    attrs: CtaAttrs
    content: List[Any] = Field(default_factory=list)


class DividerAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: Literal["line", "dots", "glyph"] = "line"


class Divider(_Base):
    type: Literal["divider"]
    attrs: DividerAttrs = Field(default_factory=DividerAttrs)
    content: List[Any] = Field(default_factory=list)


class EmbedAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["linkedin", "x"]
    url: str
    title: Optional[str] = None
    preview_text: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _u(cls, v: str) -> str:
        if not re.match(r"^https://(www\.)?(linkedin\.com|x\.com|twitter\.com)/", v):
            raise ValueError("embed url must be a linkedin.com or x.com URL")
        return v


class Embed(_Base):
    type: Literal["embed"]
    attrs: EmbedAttrs
    content: List[Any] = Field(default_factory=list)


class LegacyHtmlAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: str
    source: Literal["markdown", "html"] = "html"


class LegacyHtml(_Base):
    """Migration only. Wraps an existing article; sanitised through an
    allowlist on render, never passed through raw."""
    type: Literal["legacy_html"]
    attrs: LegacyHtmlAttrs
    content: List[Any] = Field(default_factory=list)


Block = Annotated[
    Union[Paragraph, Heading, KeyTakeaways, ListBlock, Steps, Image, Gallery,
          CompareSlider, Video, Table, Callout, Quote, Code, StatBand, Chart,
          ProcessFlow, Faq, Cta, Divider, Embed, LegacyHtml],
    Field(discriminator="type"),
]

BLOCK_TYPES = ("paragraph", "heading", "key_takeaways", "list", "steps", "image",
               "gallery", "compare_slider", "video", "table", "callout", "quote",
               "code", "stat_band", "chart", "process_flow", "faq", "cta",
               "divider", "embed", "legacy_html")


class _Doc(BaseModel):
    blocks: List[Block]


def parse_blocks(raw: Any) -> List[Block]:
    """Validate a raw block array. Raises BlockError naming block and field."""
    if not isinstance(raw, list):
        raise BlockError("content_blocks must be a list")
    seen: Dict[str, int] = {}
    for i, b in enumerate(raw):
        if isinstance(b, dict):
            bid = b.get("id")
            if isinstance(bid, str):
                if bid in seen:
                    raise BlockError(
                        f"duplicate block id {bid!r} at positions {seen[bid]} and {i}")
                seen[bid] = i
    try:
        return _Doc(blocks=raw).blocks
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = first.get("loc", ())
        index = next((p for p in loc if isinstance(p, int)), None)
        bid = None
        if index is not None and index < len(raw) and isinstance(raw[index], dict):
            bid = raw[index].get("id")
        # Drop the discriminator tag and positional parts so the path reads
        # like attrs.alt rather than blocks.3.image.attrs.alt.
        parts = [str(p) for p in loc if not isinstance(p, int) and p != "blocks"]
        if parts and parts[0] in BLOCK_TYPES:
            parts = parts[1:]
        where = f"block {bid or index}"
        path = ".".join(parts) or "(block)"
        raise BlockError(f"{where}: {path}: {first.get('msg')}") from None
