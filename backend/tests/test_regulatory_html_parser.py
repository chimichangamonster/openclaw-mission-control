# ruff: noqa: INP001
"""Unit tests for ``regulatory_html_parser`` (item 101 v2 Phase 1b.2).

Tests the deterministic HTML parser that turns ``equipment-tracker.html``
into a ParsedTracker intermediate form. The importer endpoint is tested
separately in ``test_regulatory_import_html.py`` — these tests lock the
parser contract end-to-end on hand-crafted fixture snippets that mirror
the real tracker's structure.

Coverage focus:
- Country panel detection + skipping unpublished countries
- Stream extraction (Canada layout vs prefixed-id layout)
- Phase extraction with badge_kind + default_open
- Task extraction with text + note + tags
- Priority note severity classification
- Idempotent body_hash across whitespace/case noise
"""

from __future__ import annotations

from app.services.regulatory_html_parser import (
    ParsedTask,
    parse_tracker_html,
)

# ---------------------------------------------------------------------------
# Fixture builders — mirror the real tracker's tag shapes
# ---------------------------------------------------------------------------


def _wrap_panel(country_html_id: str, body: str) -> str:
    return (
        f'<div class="tab-panel" id="panel-{country_html_id}" '
        f'data-country-label="{country_html_id.title()}">'
        f"{body}</div>"
    )


def _wrap_stream(stream_id: str, color: str, title: str, body: str) -> str:
    return (
        f'<div id="{stream_id}">'
        f'<div class="stream-header {color}">'
        f'<div class="stream-title">{title}</div>'
        f'<div class="stream-subtitle">Sub</div>'
        f'<div class="stream-budget">Budget: $100K · Regulator: ABSA</div>'
        f"</div>"
        f"{body}</div>"
    )


def _phase(name: str, badge: str, *items: str, open_: bool = False) -> str:
    open_class = " open" if open_ else ""
    items_html = "".join(items)
    return (
        f'<div class="phase-block">'
        f'<div class="phase-title-row{open_class}" data-phase-toggle>'
        f'<span class="phase-badge badge-{badge}">Label</span>'
        f'<span class="phase-name">{name}</span>'
        f'<span class="phase-timing">Days 1-10</span>'
        f"</div>"
        f'<div class="phase-items{open_class}">{items_html}</div>'
        f"</div>"
    )


def _task(text: str, note: str | None = None, *tag_specs: tuple[str, str]) -> str:
    note_html = f'<div class="task-note">{note}</div>' if note else ""
    tags_html = "".join(
        f'<span class="tag tag-{slug}">{label}</span>' for slug, label in tag_specs
    )
    return (
        '<div class="task-item" data-task-toggle>'
        '<div class="task-check"></div>'
        '<div class="task-body">'
        f'<div class="task-text">{text}</div>'
        f"{note_html}"
        f'<div class="task-tags">{tags_html}</div>'
        "</div></div>"
    )


def _priority_note(severity: str, body: str) -> str:
    return f'<div class="priority-note {severity}">{body}</div>'


# ---------------------------------------------------------------------------
# Country detection
# ---------------------------------------------------------------------------


def test_canada_panel_is_extracted_with_iso_code() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream("stream-navy", "navy", "Corporate", _phase("P1", "corp")),
    )
    result = parse_tracker_html(html)
    assert len(result.countries) == 1
    assert result.countries[0].code == "CA"
    assert "Canada" in result.countries[0].display_label


def test_unpublished_panels_are_silently_skipped() -> None:
    """India and Kenya panels are not in PUBLISHED_COUNTRIES — skip them."""
    html = (
        _wrap_panel("canada", _wrap_stream("stream-navy", "navy", "Corp", _phase("P", "corp")))
        + _wrap_panel(
            "india",
            _wrap_stream(
                "india-stream-navy", "navy", "Indian Entry", _phase("IP", "now")
            ),
        )
        + _wrap_panel("kenya", "")
    )
    result = parse_tracker_html(html)
    assert [c.code for c in result.countries] == ["CA"]


# ---------------------------------------------------------------------------
# Stream extraction
# ---------------------------------------------------------------------------


def test_stream_slug_strips_canada_prefix() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream("stream-green", "green", "Eboiler", _phase("P", "corp")),
    )
    result = parse_tracker_html(html)
    assert result.countries[0].streams[0].slug == "green"
    assert result.countries[0].streams[0].name == "Eboiler"
    assert result.countries[0].streams[0].color_token == "green"


def test_stream_color_token_from_header_class() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream("stream-orange", "orange", "MagnetGas", _phase("P", "corp")),
    )
    stream = parse_tracker_html(html).countries[0].streams[0]
    assert stream.color_token == "orange"


def test_multiple_streams_within_one_country() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream("stream-navy", "navy", "Corp", _phase("P1", "corp"))
        + _wrap_stream("stream-green", "green", "Eboiler", _phase("P2", "now"))
        + _wrap_stream("stream-orange", "orange", "MagnetGas", _phase("P3", "now")),
    )
    streams = parse_tracker_html(html).countries[0].streams
    assert [s.slug for s in streams] == ["navy", "green", "orange"]


# ---------------------------------------------------------------------------
# Phase extraction
# ---------------------------------------------------------------------------


def test_phase_extracts_name_and_badge_kind() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corporate",
            _phase("Incorporate Magnetik", "corp"),
        ),
    )
    phase = parse_tracker_html(html).countries[0].streams[0].phases[0]
    assert phase.name == "Incorporate Magnetik"
    assert phase.badge_kind == "corp"


def test_phase_default_open_from_open_class() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corporate",
            _phase("Default Open", "corp", open_=True)
            + _phase("Default Closed", "post", open_=False),
        ),
    )
    phases = parse_tracker_html(html).countries[0].streams[0].phases
    assert phases[0].default_open is True
    assert phases[1].default_open is False


def test_unknown_badge_kind_falls_back_to_now() -> None:
    """The CSS could ship a new badge class before the model knows it.
    Don't crash — degrade gracefully to "now"."""
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corp",
            '<div class="phase-block">'
            '<div class="phase-title-row" data-phase-toggle>'
            '<span class="phase-badge badge-supernova-2030">x</span>'
            '<span class="phase-name">P</span>'
            "</div>"
            '<div class="phase-items"></div>'
            "</div>",
        ),
    )
    phase = parse_tracker_html(html).countries[0].streams[0].phases[0]
    assert phase.badge_kind == "now"


# ---------------------------------------------------------------------------
# Task extraction
# ---------------------------------------------------------------------------


def test_task_with_text_note_and_tags() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corp",
            _phase(
                "P",
                "corp",
                _task(
                    "NUANS name search",
                    "Reserves the name for 90 days.",
                    ("corp", "ABCA"),
                    ("critical", "Day 1"),
                ),
            ),
        ),
    )
    task = parse_tracker_html(html).countries[0].streams[0].phases[0].tasks[0]
    assert task.text == "NUANS name search"
    assert task.note == "Reserves the name for 90 days."
    assert [(t.slug, t.label) for t in task.tags] == [
        ("corp", "ABCA"),
        ("critical", "Day 1"),
    ]


def test_task_without_note_or_tags() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corp",
            _phase("P", "corp", _task("Standalone task")),
        ),
    )
    task = parse_tracker_html(html).countries[0].streams[0].phases[0].tasks[0]
    assert task.text == "Standalone task"
    assert task.note is None
    assert task.tags == []


def test_multiple_tasks_in_phase_preserve_order() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corp",
            _phase(
                "P",
                "corp",
                _task("First"),
                _task("Second"),
                _task("Third"),
            ),
        ),
    )
    tasks = parse_tracker_html(html).countries[0].streams[0].phases[0].tasks
    assert [t.text for t in tasks] == ["First", "Second", "Third"]


# ---------------------------------------------------------------------------
# Priority notes
# ---------------------------------------------------------------------------


def test_priority_note_severity_from_class() -> None:
    html = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corp",
            _phase(
                "P",
                "corp",
                _priority_note("critical", "BLOCKING ITEM"),
                _priority_note("navy-note", "Process note"),
                _priority_note("warn", "Caution"),
                _priority_note("info", "FYI"),
                _task("a task"),  # mixed-content phase
            ),
        ),
    )
    notes = parse_tracker_html(html).countries[0].streams[0].phases[0].priority_notes
    severities = [n.severity for n in notes]
    assert severities == ["critical", "navy-note", "warn", "info"]


# ---------------------------------------------------------------------------
# Idempotency hash
# ---------------------------------------------------------------------------


def test_body_hash_stable_across_whitespace_noise() -> None:
    """Hash is computed over collapsed-whitespace, lowercased text — so
    trivial editorial whitespace changes don't create duplicates on re-import."""
    a = ParsedTask.make("File Annual Return", None, [])
    b = ParsedTask.make("  File   Annual\nReturn  ", None, [])
    c = ParsedTask.make("file annual return", None, [])
    assert a.body_hash == b.body_hash == c.body_hash


def test_body_hash_changes_on_substantive_text_change() -> None:
    a = ParsedTask.make("File Annual Return with Alberta", None, [])
    b = ParsedTask.make("File Annual Return with CRA", None, [])
    assert a.body_hash != b.body_hash


# ---------------------------------------------------------------------------
# Real-world fixture — verify against the actual file shape via a slice
# ---------------------------------------------------------------------------


def test_real_world_canada_corporate_first_task() -> None:
    """Anchor test against a chunk that mirrors equipment-tracker.html lines
    188-198 (the first phase under the navy/Corporate stream). Verifies the
    parser handles the real shape, not just our synthesized fixtures."""
    real_chunk = _wrap_panel(
        "canada",
        _wrap_stream(
            "stream-navy",
            "navy",
            "Corporate Structure, Incorporation &amp; Legal Foundation",
            '<div class="phase-block">'
            '<div class="phase-title-row open" data-phase-toggle>'
            '<span class="phase-badge badge-corp">Urgent — This Week</span>'
            '<span class="phase-name">Incorporate Magnetik Solutions Inc. (Alberta)</span>'
            '<span class="phase-timing">Days 1–10</span>'
            '<span class="phase-chevron">▼</span>'
            "</div>"
            '<div class="phase-items open">'
            '<div class="priority-note critical">🚫 BLOCKING ITEM: '
            "No regulatory submission may be filed until incorporated.</div>"
            '<div class="task-item" data-task-toggle>'
            '<div class="task-check"></div>'
            '<div class="task-body">'
            '<div class="task-text">Conduct NUANS name search for "Magnetik Solutions Inc."</div>'
            '<div class="task-note">Required before filing Articles of Incorporation. '
            "Reserves the name for 90 days. Cost ~$50.</div>"
            '<div class="task-tags">'
            '<span class="tag tag-corp">ABCA</span>'
            '<span class="tag tag-critical">Day 1</span>'
            "</div></div></div>"
            "</div></div>",
        ),
    )
    result = parse_tracker_html(real_chunk)
    country = result.countries[0]
    assert country.code == "CA"
    stream = country.streams[0]
    assert stream.slug == "navy"
    assert stream.name.startswith("Corporate Structure")
    assert stream.color_token == "navy"
    phase = stream.phases[0]
    assert phase.name.startswith("Incorporate Magnetik")
    assert phase.badge_kind == "corp"
    assert phase.default_open is True
    assert phase.timing_label == "Days 1–10"
    assert len(phase.priority_notes) == 1
    assert phase.priority_notes[0].severity == "critical"
    assert "BLOCKING" in phase.priority_notes[0].body
    assert len(phase.tasks) == 1
    task = phase.tasks[0]
    assert "NUANS" in task.text
    assert task.note is not None and "90 days" in task.note
    assert {(t.slug, t.label) for t in task.tags} == {
        ("corp", "ABCA"),
        ("critical", "Day 1"),
    }
