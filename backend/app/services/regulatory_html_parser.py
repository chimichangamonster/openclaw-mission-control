"""Deterministic HTML parser for ``equipment-tracker.html`` (item 101 v2 Phase 1b.2).

Reads the structured HTML produced by the magnetik-solutions marketing-site
tracker and emits a normalized intermediate form that the import-html endpoint
stitches into the regulatory tracker tables.

Design decisions:

- **stdlib only** — uses ``html.parser.HTMLParser``. No bs4 / lxml / Selenium
  / LLM dependency. The structure is regular and well-formed enough that
  classic state-machine parsing handles every observed shape.

- **Deterministic** per ``feedback_determinism_first_for_high_liability.md``:
  this seeds Henry's regulatory workflow, where errors translate to missed
  filings or grant deadlines. No fuzzy matching, no AI normalization.

- **Idempotency hash** is computed over normalized ``task_text`` (collapsed
  whitespace, lowercased). Re-running the parser on the same HTML returns
  identical hashes; the import endpoint uses
  ``(country_code, stream_slug, phase_name, task_body_hash)`` as a uniqueness
  tuple to deduplicate re-imports.

- **HTML entities** are decoded by the parser (e.g. ``&amp;`` → ``&``,
  ``&middot;`` → ``·``). Emoji code points pass through unchanged.

- **Country mapping** is hardcoded: only ``canada → CA`` is processed for
  the v2 ship per scoping decision (operator confirmed Canada-only).
  India + Kenya panels in the source HTML are silently skipped — they get
  parsed when an org expands beyond Canada.

Implementation note — the parser uses a single explicit ``<div>`` stack so
each opening tag pushes a typed frame and the matching close pops it,
eliminating the depth-counter bugs that an ad-hoc multi-counter approach
suffers from when text-collecting leaf divs (.task-text, .stream-title,
.priority-note, etc.) are interleaved with structural ones.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Public scope — only Canada is published in v2 (operator-confirmed).
# Extending to IN/KE later is a config map change, not a parser change.
# ---------------------------------------------------------------------------

PUBLISHED_COUNTRIES: dict[str, tuple[str, str]] = {
    # html_country_id  →  (iso_code, display_label)
    "canada": ("CA", "Canada (Alberta Pilot)"),
}

# Phase badge kinds the model accepts, derived from ``badge-{kind}`` class.
# Map silently unknown badges to the generic "now" rather than fail the import.
_BADGE_KINDS = {
    "now",
    "pre",
    "arrive",
    "post",
    "concurrent",
    "corp",
    "insurance",
}

# Priority note severities the model accepts.
_NOTE_SEVERITIES = {"critical", "info", "warn", "navy-note"}


# ---------------------------------------------------------------------------
# Intermediate form — what the parser emits, what the importer consumes
# ---------------------------------------------------------------------------


@dataclass
class ParsedTag:
    slug: str  # e.g. "abca", "absa", "csa" — derived from class "tag-{slug}"
    label: str  # display label, e.g. "ABCA"


@dataclass
class ParsedPriorityNote:
    body: str
    severity: str  # critical | info | warn | navy-note


@dataclass
class ParsedTask:
    text: str  # the task-text element body
    note: str | None  # optional task-note element body
    tags: list[ParsedTag]
    body_hash: str  # SHA-256 of normalized text — the dedup key

    @classmethod
    def make(cls, text: str, note: str | None, tags: list[ParsedTag]) -> ParsedTask:
        return cls(text=text, note=note, tags=tags, body_hash=_hash_task_text(text))


@dataclass
class ParsedPhase:
    name: str
    badge_kind: str  # mapped to _BADGE_KINDS or "now"
    timing_label: str | None
    default_open: bool  # true if the phase-title-row had "open" class
    priority_notes: list[ParsedPriorityNote] = field(default_factory=list)
    tasks: list[ParsedTask] = field(default_factory=list)


@dataclass
class ParsedStream:
    slug: str  # navy | green | orange | eboiler — country prefix stripped
    name: str  # stream-title text
    color_token: str  # green | orange | navy — from stream-header class
    subtitle: str | None  # stream-subtitle text
    budget_blob: str | None  # raw stream-budget text (regulator/timeline parsed downstream)
    phases: list[ParsedPhase] = field(default_factory=list)


@dataclass
class ParsedCountry:
    code: str  # ISO-2 — CA
    display_label: str  # "Canada (Alberta Pilot)"
    streams: list[ParsedStream] = field(default_factory=list)


@dataclass
class ParsedTracker:
    countries: list[ParsedCountry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    """Collapse whitespace and strip — what's stored in DB."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def _hash_task_text(text: str) -> str:
    """SHA-256 of normalized + lowercased task text — the dedup key.

    Lowercase + whitespace-collapse so trivial edits don't create duplicates.
    Hash is stable across runs of the parser on the same logical content.
    """
    normalized = _normalize_text(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    for name, value in attrs:
        if name == "class" and value:
            return set(value.split())
    return set()


def _attr(attrs: list[tuple[str, str | None]], name: str) -> str | None:
    for attr_name, value in attrs:
        if attr_name == name:
            return value
    return None


def _badge_kind_from_classes(classes: set[str]) -> str:
    for cls in classes:
        if cls.startswith("badge-"):
            kind = cls.removeprefix("badge-")
            if kind in _BADGE_KINDS:
                return kind
    return "now"


def _stream_color_from_header_classes(classes: set[str]) -> str:
    for color in ("green", "orange", "navy", "purple"):
        if color in classes:
            return color
    return "navy"


def _priority_severity_from_classes(classes: set[str]) -> str:
    for severity in _NOTE_SEVERITIES:
        if severity in classes:
            return severity
    return "info"


def _tag_slug_from_classes(classes: set[str]) -> str | None:
    for cls in classes:
        if cls.startswith("tag-"):
            return cls.removeprefix("tag-")
    return None


def _stream_slug_from_id(stream_id: str, country_html_id: str) -> str | None:
    """Derive stream slug from the container id.

    Canada uses ``stream-{slug}``; India/Kenya use ``{country}-stream-{slug}``.
    Returns None for ids that don't match either pattern.
    """
    canada_prefix = "stream-"
    country_prefix = f"{country_html_id}-stream-"
    if stream_id.startswith(country_prefix):
        return stream_id.removeprefix(country_prefix)
    if stream_id.startswith(canada_prefix):
        return stream_id.removeprefix(canada_prefix)
    return None


# ---------------------------------------------------------------------------
# Parser — explicit div-frame stack
# ---------------------------------------------------------------------------

# Frame kinds — what each <div> on the stack represents.
# Close-handler dispatches on this.
_FRAME_PANEL = "panel"  # <div class="tab-panel">
_FRAME_STREAM = "stream"  # <div id="stream-..."> or <div id="{country}-stream-...">
_FRAME_PHASE = "phase"  # <div class="phase-block">
_FRAME_TASK = "task"  # <div class="task-item">
_FRAME_COLLECT = "collect"  # text-collecting leaf div (task-text, priority-note, etc.)
_FRAME_OTHER = "other"  # any other <div> we don't act on


@dataclass
class _Frame:
    kind: str
    # collect-kind frames carry the buffer label so the close handler routes
    # the flushed text to the correct destination.
    collect_label: str | None = None
    collect_extra: str | None = None
    # panel frames carry whether this country is published (i.e. captured).
    published: bool = True


class _TrackerParser(HTMLParser):
    """State-machine parser using an explicit <div> frame stack."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tracker = ParsedTracker()

        # Active context (None when not inside that scope).
        self._country: ParsedCountry | None = None
        self._country_html_id: str | None = None
        self._stream: ParsedStream | None = None
        self._phase: ParsedPhase | None = None

        # Pending task being built — flushed on close of TASK frame.
        self._task_text: str | None = None
        self._task_note: str | None = None
        self._task_tags: list[ParsedTag] = []

        # Stack of open <div> frames.
        self._div_stack: list[_Frame] = []

        # Span-collect state — spans don't push frames (we never need to
        # enforce nested-span structure), just direct begin/end on tag pair.
        self._span_collecting: str | None = None
        self._span_buffer: list[str] = []
        self._pending_tag_slug: str | None = None

        # Div-collect buffer (for collect-kind frames).
        self._div_buffer: list[str] = []

    # -- tag handlers ------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        cls = _classes(attrs)

        if tag == "span":
            self._handle_span_open(cls)
            return

        if tag == "div":
            self._handle_div_open(cls, attrs)
            return

    def _handle_span_open(self, cls: set[str]) -> None:
        if "phase-name" in cls and self._phase is not None:
            self._begin_span_collect("phase-name")
            return
        if "phase-timing" in cls and self._phase is not None:
            self._begin_span_collect("phase-timing")
            return
        if "phase-badge" in cls and self._phase is not None:
            # badge_kind is derived from the class itself, not the visible label.
            self._phase.badge_kind = _badge_kind_from_classes(cls)
            return
        if (
            "tag" in cls
            and self._task_text is not None
            or ("tag" in cls and self._div_stack and self._div_stack[-1].kind == _FRAME_TASK)
        ):
            # Tag spans appear inside task-tags inside the task body. We're
            # inside a task frame.
            slug = _tag_slug_from_classes(cls)
            if slug:
                self._pending_tag_slug = slug
                self._begin_span_collect("tag-label")
            return

    def _handle_div_open(self, cls: set[str], attrs: list[tuple[str, str | None]]) -> None:
        # ----- panel (country) ----------------------------------------------
        if "tab-panel" in cls:
            panel_id = _attr(attrs, "id") or ""
            country_html_id = panel_id.removeprefix("panel-")
            mapping = PUBLISHED_COUNTRIES.get(country_html_id)
            if mapping:
                code, label = mapping
                country = ParsedCountry(code=code, display_label=label)
                self.tracker.countries.append(country)
                self._country = country
                self._country_html_id = country_html_id
                self._div_stack.append(_Frame(kind=_FRAME_PANEL, published=True))
            else:
                self._country = None
                self._country_html_id = country_html_id
                self._div_stack.append(_Frame(kind=_FRAME_PANEL, published=False))
            return

        # If we're not inside any panel, treat as OTHER.
        if not self._div_stack or self._div_stack[0].kind != _FRAME_PANEL:
            self._div_stack.append(_Frame(kind=_FRAME_OTHER))
            return

        # If the enclosing panel is unpublished, everything inside is OTHER.
        if not self._div_stack[0].published:
            self._div_stack.append(_Frame(kind=_FRAME_OTHER))
            return

        # ----- text-collecting leaves (must be checked before structural) ---
        # These are leaves: open → buffer text → close → flush.
        # They MUST push a COLLECT frame so the close handler routes correctly.
        if "task-text" in cls and self._inside(_FRAME_TASK):
            self._begin_div_collect("task-text")
            return
        if "task-note" in cls and self._inside(_FRAME_TASK):
            self._begin_div_collect("task-note")
            return
        if "stream-title" in cls and self._stream is not None:
            self._begin_div_collect("stream-title")
            return
        if "stream-subtitle" in cls and self._stream is not None:
            self._begin_div_collect("stream-subtitle")
            return
        if "stream-budget" in cls and self._stream is not None:
            self._begin_div_collect("stream-budget")
            return
        if "priority-note" in cls and self._phase is not None:
            severity = _priority_severity_from_classes(cls)
            self._begin_div_collect("priority-note", extra=severity)
            return

        # ----- stream entry (id-based) --------------------------------------
        if (
            self._country is not None
            and self._country_html_id is not None
            and self._stream is None
            and self._phase is None
        ):
            div_id = _attr(attrs, "id")
            if div_id:
                slug = _stream_slug_from_id(div_id, self._country_html_id)
                if slug:
                    stream = ParsedStream(
                        slug=slug,
                        name="",
                        color_token="navy",
                        subtitle=None,
                        budget_blob=None,
                    )
                    self._country.streams.append(stream)
                    self._stream = stream
                    self._div_stack.append(_Frame(kind=_FRAME_STREAM))
                    return

        # ----- stream-header (just sets color, OTHER frame) -----------------
        if "stream-header" in cls and self._stream is not None:
            self._stream.color_token = _stream_color_from_header_classes(cls)
            self._div_stack.append(_Frame(kind=_FRAME_OTHER))
            return

        # ----- phase entry --------------------------------------------------
        if "phase-block" in cls and self._stream is not None:
            phase = ParsedPhase(
                name="",
                badge_kind="now",
                timing_label=None,
                default_open=False,
            )
            self._stream.phases.append(phase)
            self._phase = phase
            self._div_stack.append(_Frame(kind=_FRAME_PHASE))
            return

        # ----- phase-title-row (carries default_open class + child spans) ---
        if "phase-title-row" in cls and self._phase is not None:
            self._phase.default_open = "open" in cls
            self._div_stack.append(_Frame(kind=_FRAME_OTHER))
            return

        # ----- task entry ---------------------------------------------------
        if "task-item" in cls and self._phase is not None:
            self._task_text = None
            self._task_note = None
            self._task_tags = []
            self._div_stack.append(_Frame(kind=_FRAME_TASK))
            return

        # ----- everything else ----------------------------------------------
        self._div_stack.append(_Frame(kind=_FRAME_OTHER))

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._end_span_collect()
            return

        if tag == "div" and self._div_stack:
            frame = self._div_stack.pop()
            self._close_frame(frame)
            return

    def _close_frame(self, frame: _Frame) -> None:
        if frame.kind == _FRAME_COLLECT:
            self._flush_div_collect(frame)
            return

        if frame.kind == _FRAME_TASK and self._phase is not None:
            if self._task_text is not None:
                self._phase.tasks.append(
                    ParsedTask.make(
                        text=_normalize_text(self._task_text),
                        note=_normalize_text(self._task_note) if self._task_note else None,
                        tags=list(self._task_tags),
                    )
                )
            self._task_text = None
            self._task_note = None
            self._task_tags = []
            return

        if frame.kind == _FRAME_PHASE:
            self._phase = None
            return

        if frame.kind == _FRAME_STREAM:
            self._stream = None
            return

        if frame.kind == _FRAME_PANEL:
            self._country = None
            self._country_html_id = None
            return

    def handle_data(self, data: str) -> None:
        if self._span_collecting is not None:
            self._span_buffer.append(data)
            return
        # Active div-collect = topmost frame is COLLECT.
        if self._div_stack and self._div_stack[-1].kind == _FRAME_COLLECT:
            self._div_buffer.append(data)

    # -- collect helpers ---------------------------------------------------

    def _begin_div_collect(self, label: str, extra: str | None = None) -> None:
        self._div_buffer = []
        self._div_stack.append(
            _Frame(kind=_FRAME_COLLECT, collect_label=label, collect_extra=extra)
        )

    def _flush_div_collect(self, frame: _Frame) -> None:
        text = _normalize_text("".join(self._div_buffer))
        self._div_buffer = []
        label = frame.collect_label
        extra = frame.collect_extra

        if label == "task-text" and self._inside(_FRAME_TASK):
            self._task_text = text
            return
        if label == "task-note" and self._inside(_FRAME_TASK):
            self._task_note = text
            return
        if label == "stream-title" and self._stream is not None:
            self._stream.name = text
            return
        if label == "stream-subtitle" and self._stream is not None:
            self._stream.subtitle = text or None
            return
        if label == "stream-budget" and self._stream is not None:
            self._stream.budget_blob = text or None
            return
        if label == "priority-note" and self._phase is not None:
            severity = extra or "info"
            self._phase.priority_notes.append(ParsedPriorityNote(body=text, severity=severity))
            return

    def _begin_span_collect(self, label: str) -> None:
        self._span_collecting = label
        self._span_buffer = []

    def _end_span_collect(self) -> None:
        if self._span_collecting is None:
            return
        text = _normalize_text("".join(self._span_buffer))
        label = self._span_collecting
        self._span_collecting = None
        self._span_buffer = []

        if label == "phase-name" and self._phase is not None:
            self._phase.name = text
            return
        if label == "phase-timing" and self._phase is not None:
            self._phase.timing_label = text or None
            return
        if label == "tag-label" and self._inside(_FRAME_TASK):
            slug = self._pending_tag_slug
            self._pending_tag_slug = None
            if slug:
                self._task_tags.append(ParsedTag(slug=slug, label=text))
            return

    def _inside(self, kind: str) -> bool:
        return any(f.kind == kind for f in self._div_stack)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def parse_tracker_html(html: str) -> ParsedTracker:
    """Parse equipment-tracker.html into a ParsedTracker.

    Returns a ParsedTracker with one ParsedCountry per published country
    (currently just Canada). Raises no exceptions on malformed input —
    bad sections are silently skipped and the importer can decide whether
    a sparse result is an error.
    """
    parser = _TrackerParser()
    parser.feed(html)
    parser.close()
    return parser.tracker


# ---------------------------------------------------------------------------
# Tag taxonomy helpers (used by importer to seed RegulatoryTag rows)
# ---------------------------------------------------------------------------

_TAG_KIND_BY_SLUG = {
    "corp": "corporate",
    "legal": "legal",
    "grant": "grant",
    "absa": "regulatory",
    "csa": "regulatory",
    "aep": "regulatory",
    "abca": "regulatory",
    "insurance": "insurance",
    "critical": "priority",
}


def kind_for_tag_slug(slug: str) -> str:
    """Return the RegulatoryTag.kind value for a parsed tag slug."""
    return _TAG_KIND_BY_SLUG.get(slug, "regulatory")
