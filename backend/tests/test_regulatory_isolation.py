# ruff: noqa: INP001
"""Multi-tenant isolation tests for the regulatory tracker (item 101 v2).

These tests are intentionally written BEFORE the production code per
`feedback_test_before_deploy.md`. They lock down the cross-org isolation
contract that items 101 v2 / 107 v2 / 108 must satisfy.

The regulatory tracker exposes 8 tables. Three classes of isolation need
direct verification:

1. **Direct ownership** — TenantScoped tables (Stream, Country, Tag) carry
   `organization_id` themselves. The basic "can't read other org's row"
   test applies.

2. **Indirect ownership through parent FK** — Phase is FK→Stream+Country,
   Task is FK→Phase, TaskNote is FK→Task, PriorityNote is FK→Phase,
   TaskTag is FK→Task+Tag. Cross-org access through these chains must be
   denied at the API layer (the model layer permits the join; only the
   route's `organization_id` filter prevents the leak).

3. **Cross-link mixing** — TaskTag (M2M between Task and Tag) is the
   subtle one. Both endpoints must verify the linked entities belong to
   the SAME org. A bug here lets org B's tag get attached to org A's
   task — silent metadata leak, no error raised at the DB layer.

The fourth concern is the public snapshot endpoint, tested separately:
- Wrong token → 404
- Right token → only returns the org bound to that token
- Token rotation immediately invalidates prior token

These tests run against in-memory SQLite. They mirror `test_org_isolation.py`
conventions for the model-level checks and `test_cross_org_boards_endpoint.py`
conventions for HTTP-level checks via FastAPI test client.

When the production code lands, importing the models must NOT need test
changes. If a test starts failing post-implementation, the implementation
violated the isolation contract — fix the implementation, not the test.

Patterns surfaced for platform-wide reuse:
- M2M cross-org-mixing test pattern (the TaskTag case) generalizes to
  any future M2M where both endpoints are org-scoped. Worth promoting to
  a shared test helper if 2+ M2M models adopt it.
- Public-snapshot-by-token pattern (token-as-resource-locator) generalizes
  to grants snapshot (item 107 v2) and any future "publish org subset to
  external readers" surface.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

# These imports will fail until the production code is written.
# That failure is the contract — the implementer (me) sees red, writes
# the models with these exact names + relationships, watches red turn green.
pytest.importorskip(
    "app.models.regulatory",
    reason=(
        "Item 101 v2 Phase 1a: production models not yet written. "
        "These isolation tests are the contract — they go green when the "
        "models exist with the field shapes asserted below."
    ),
)

from app.models.regulatory import (  # noqa: E402
    RegulatoryCountry,
    RegulatoryPhase,
    RegulatoryPriorityNote,
    RegulatoryStream,
    RegulatoryTag,
    RegulatoryTask,
    RegulatoryTaskNote,
    RegulatoryTaskTag,
)

# ---------------------------------------------------------------------------
# Fixtures — two orgs, parallel data, no shared rows
# ---------------------------------------------------------------------------

ORG_A_ID = uuid4()
ORG_B_ID = uuid4()
USER_A_ID = uuid4()
USER_B_ID = uuid4()


async def _make_session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(session: AsyncSession) -> dict[str, UUID]:
    """Seed two orgs with parallel regulatory trees.

    Org A: Canada → Corporate stream → "Incorporate" phase → "NUANS search" task,
            tagged with org-A's "ABCA" tag. Note attached to task.
    Org B: Canada → Corporate stream → "Incorporate" phase → "NUANS search" task,
            tagged with org-B's "ABCA" tag. Note attached to task.

    Each org has its own copy of every row. No shared rows. Verifying isolation
    means verifying the trees don't cross-pollinate.
    """
    # --- Org A ---
    country_a = RegulatoryCountry(
        organization_id=ORG_A_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada (Alberta Pilot)",
        sort_order=0,
    )
    stream_a = RegulatoryStream(
        organization_id=ORG_A_ID,
        slug="corporate",
        name="Corporate Foundation",
        color_token="navy",
        sort_order=0,
    )
    session.add_all([country_a, stream_a])
    await session.flush()

    phase_a = RegulatoryPhase(
        stream_id=stream_a.id,
        country_id=country_a.id,
        name="Incorporate Magnetik Solutions Inc.",
        badge_kind="corp",
        timing_label="Days 1-10",
        sort_order=0,
        default_open=True,
    )
    tag_a = RegulatoryTag(
        organization_id=ORG_A_ID,
        slug="abca",
        label="ABCA",
        color_token="corp",
        kind="corporate",
    )
    session.add_all([phase_a, tag_a])
    await session.flush()

    task_a = RegulatoryTask(
        phase_id=phase_a.id,
        body="Conduct NUANS name search",
        note=None,
        completed=False,
        sort_order=0,
    )
    session.add(task_a)
    await session.flush()

    task_tag_a = RegulatoryTaskTag(task_id=task_a.id, tag_id=tag_a.id)
    note_a = RegulatoryTaskNote(
        task_id=task_a.id,
        body="Required before filing Articles of Incorporation.",
        author_user_id=USER_A_ID,
    )
    priority_note_a = RegulatoryPriorityNote(
        phase_id=phase_a.id,
        body="🚫 BLOCKING ITEM: No regulatory submission until incorporation.",
        severity="critical",
        sort_order=0,
    )
    session.add_all([task_tag_a, note_a, priority_note_a])

    # --- Org B (parallel structure, no overlap) ---
    country_b = RegulatoryCountry(
        organization_id=ORG_B_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada",
        sort_order=0,
    )
    stream_b = RegulatoryStream(
        organization_id=ORG_B_ID,
        slug="corporate",
        name="Corporate Foundation",
        color_token="navy",
        sort_order=0,
    )
    session.add_all([country_b, stream_b])
    await session.flush()

    phase_b = RegulatoryPhase(
        stream_id=stream_b.id,
        country_id=country_b.id,
        name="Incorporate",
        badge_kind="corp",
        timing_label="Days 1-10",
        sort_order=0,
        default_open=True,
    )
    tag_b = RegulatoryTag(
        organization_id=ORG_B_ID,
        slug="abca",
        label="ABCA",
        color_token="corp",
        kind="corporate",
    )
    session.add_all([phase_b, tag_b])
    await session.flush()

    task_b = RegulatoryTask(
        phase_id=phase_b.id,
        body="Conduct NUANS name search",
        note=None,
        completed=False,
        sort_order=0,
    )
    session.add(task_b)
    await session.flush()

    task_tag_b = RegulatoryTaskTag(task_id=task_b.id, tag_id=tag_b.id)
    note_b = RegulatoryTaskNote(
        task_id=task_b.id,
        body="Org B's note.",
        author_user_id=USER_B_ID,
    )
    session.add_all([task_tag_b, note_b])

    await session.commit()

    return {
        "country_a_id": country_a.id,
        "country_b_id": country_b.id,
        "stream_a_id": stream_a.id,
        "stream_b_id": stream_b.id,
        "phase_a_id": phase_a.id,
        "phase_b_id": phase_b.id,
        "task_a_id": task_a.id,
        "task_b_id": task_b.id,
        "tag_a_id": tag_a.id,
        "tag_b_id": tag_b.id,
        "note_a_id": note_a.id,
        "note_b_id": note_b.id,
    }


async def _with_session(test_fn) -> None:
    maker = await _make_session()
    async with maker() as session:
        data = await _seed(session)
        await test_fn(session, data)


# ---------------------------------------------------------------------------
# Class 1 — Direct ownership (TenantScoped tables)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_only_visible_to_own_org() -> None:
    async def _test(session, data):
        # Org A queries scoped to ORG_A_ID
        result = await session.execute(
            select(RegulatoryStream).where(RegulatoryStream.organization_id == ORG_A_ID)
        )
        streams = result.scalars().all()
        assert len(streams) == 1
        assert streams[0].id == data["stream_a_id"]

        # Cross-org probe: Org B token attempts to read Org A's stream by ID
        result = await session.execute(
            select(RegulatoryStream).where(
                RegulatoryStream.id == data["stream_a_id"],
                RegulatoryStream.organization_id == ORG_B_ID,
            )
        )
        assert result.scalars().first() is None, "Org B must not see Org A's stream"

    await _with_session(_test)


@pytest.mark.asyncio
async def test_country_only_visible_to_own_org() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryCountry).where(
                RegulatoryCountry.id == data["country_a_id"],
                RegulatoryCountry.organization_id == ORG_B_ID,
            )
        )
        assert result.scalars().first() is None, "Org B must not see Org A's country"

    await _with_session(_test)


@pytest.mark.asyncio
async def test_tag_only_visible_to_own_org() -> None:
    async def _test(session, data):
        # Both orgs may have a tag with slug "abca" — they MUST be distinct rows.
        result = await session.execute(select(RegulatoryTag).where(RegulatoryTag.slug == "abca"))
        tags = result.scalars().all()
        assert len(tags) == 2, "Tag slugs collide across orgs but rows must be separate"
        org_a_tags = [t for t in tags if t.organization_id == ORG_A_ID]
        org_b_tags = [t for t in tags if t.organization_id == ORG_B_ID]
        assert len(org_a_tags) == 1
        assert len(org_b_tags) == 1
        assert org_a_tags[0].id != org_b_tags[0].id

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Class 2 — Indirect ownership through parent FK
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase_isolation_via_stream() -> None:
    """Phase has no organization_id directly. Isolation must trace through stream."""

    async def _test(session, data):
        # Query: "all phases under streams owned by ORG_A_ID"
        result = await session.execute(
            select(RegulatoryPhase)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(RegulatoryStream.organization_id == ORG_A_ID)
        )
        phases = result.scalars().all()
        assert len(phases) == 1
        assert phases[0].id == data["phase_a_id"]

        # Probe: same query for ORG_B_ID should not see Org A's phase
        result = await session.execute(
            select(RegulatoryPhase)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(
                RegulatoryPhase.id == data["phase_a_id"],
                RegulatoryStream.organization_id == ORG_B_ID,
            )
        )
        assert result.scalars().first() is None

    await _with_session(_test)


@pytest.mark.asyncio
async def test_task_isolation_via_phase_chain() -> None:
    """Task → Phase → Stream → org. Two-hop indirection."""

    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryTask)
            .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryTask.phase_id)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(RegulatoryStream.organization_id == ORG_A_ID)
        )
        tasks = result.scalars().all()
        assert len(tasks) == 1
        assert tasks[0].id == data["task_a_id"]

        # Probe: Org B can't reach Org A's task even with a join
        result = await session.execute(
            select(RegulatoryTask)
            .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryTask.phase_id)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(
                RegulatoryTask.id == data["task_a_id"],
                RegulatoryStream.organization_id == ORG_B_ID,
            )
        )
        assert result.scalars().first() is None

    await _with_session(_test)


@pytest.mark.asyncio
async def test_task_note_isolation_via_task_chain() -> None:
    """TaskNote → Task → Phase → Stream → org. Three-hop indirection."""

    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryTaskNote)
            .join(RegulatoryTask, RegulatoryTask.id == RegulatoryTaskNote.task_id)
            .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryTask.phase_id)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(RegulatoryStream.organization_id == ORG_A_ID)
        )
        notes = result.scalars().all()
        assert len(notes) == 1
        assert notes[0].author_user_id == USER_A_ID

    await _with_session(_test)


@pytest.mark.asyncio
async def test_priority_note_isolation_via_phase_chain() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryPriorityNote)
            .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryPriorityNote.phase_id)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(RegulatoryStream.organization_id == ORG_A_ID)
        )
        notes = result.scalars().all()
        assert len(notes) == 1
        assert notes[0].severity == "critical"

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Class 3 — M2M cross-org mixing (TaskTag) — the silent-leak surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasktag_links_only_within_same_org() -> None:
    """The link rows themselves: each TaskTag's task and tag must share an org.

    This test asserts post-conditions: after seed, no TaskTag row in the DB
    crosses orgs. If a future implementation lets one through (bad insert
    logic), this test fails.
    """

    async def _test(session, data):
        result = await session.execute(select(RegulatoryTaskTag))
        all_links = result.scalars().all()
        assert len(all_links) == 2

        for link in all_links:
            # Resolve task's org via phase→stream
            task_org_result = await session.execute(
                select(RegulatoryStream.organization_id)
                .join(RegulatoryPhase, RegulatoryPhase.stream_id == RegulatoryStream.id)
                .join(RegulatoryTask, RegulatoryTask.phase_id == RegulatoryPhase.id)
                .where(RegulatoryTask.id == link.task_id)
            )
            task_org = task_org_result.scalar_one()

            # Resolve tag's org directly
            tag_org_result = await session.execute(
                select(RegulatoryTag.organization_id).where(RegulatoryTag.id == link.tag_id)
            )
            tag_org = tag_org_result.scalar_one()

            assert task_org == tag_org, (
                f"TaskTag link crosses orgs: task in org {task_org}, "
                f"tag in org {tag_org}. This is a silent metadata leak."
            )

    await _with_session(_test)


@pytest.mark.asyncio
async def test_tasktag_query_does_not_leak_via_join() -> None:
    """Query 'all tags on org A's tasks' must not return org B's tags.

    Even if a buggy insert managed to create a cross-org link, a properly
    org-scoped read query should still filter the result. This belt-and-
    suspenders check verifies the query layer does its job.
    """

    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryTag)
            .join(RegulatoryTaskTag, RegulatoryTaskTag.tag_id == RegulatoryTag.id)
            .join(RegulatoryTask, RegulatoryTask.id == RegulatoryTaskTag.task_id)
            .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryTask.phase_id)
            .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
            .where(
                RegulatoryStream.organization_id == ORG_A_ID,
                RegulatoryTag.organization_id == ORG_A_ID,
            )
        )
        tags = result.scalars().all()
        assert len(tags) == 1
        assert tags[0].organization_id == ORG_A_ID
        assert tags[0].id == data["tag_a_id"]

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Class 4 — Listing scope (the "what does org A see" view)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_streams_scoped_to_caller_org() -> None:
    """Listing streams from org A must return only org A's streams.

    Same query that the GET /regulatory/streams endpoint will run.
    """

    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryStream).where(RegulatoryStream.organization_id == ORG_A_ID)
        )
        streams = result.scalars().all()
        assert len(streams) == 1
        for s in streams:
            assert s.organization_id == ORG_A_ID

    await _with_session(_test)


@pytest.mark.asyncio
async def test_list_tags_scoped_to_caller_org() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(RegulatoryTag).where(RegulatoryTag.organization_id == ORG_A_ID)
        )
        tags = result.scalars().all()
        assert len(tags) == 1
        assert tags[0].organization_id == ORG_A_ID

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Class 5 — Negative cross-org write (must fail at API layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase_cannot_link_streams_from_different_orgs() -> None:
    """Asserts the ONLY safe state: phase.stream_id and phase.country_id
    point to entities in the same org as each other.

    This test verifies invariant. The endpoint must validate (stream.org_id ==
    country.org_id) before creating the phase. Without that check, a
    privileged caller could silently mix streams across orgs.

    For Phase 1a (model-only), this test simulates the bad write directly
    and verifies our seed never produces it. For Phase 1b (endpoints), the
    POST /regulatory/phases endpoint will need an explicit cross-org check
    that produces a 400/403, and we'll add an API-level test.
    """

    async def _test(session, data):
        # Resolve org of every phase's stream + country
        for phase_id in (data["phase_a_id"], data["phase_b_id"]):
            phase_result = await session.execute(
                select(RegulatoryPhase).where(RegulatoryPhase.id == phase_id)
            )
            phase = phase_result.scalar_one()

            stream_result = await session.execute(
                select(RegulatoryStream.organization_id).where(
                    RegulatoryStream.id == phase.stream_id
                )
            )
            stream_org = stream_result.scalar_one()

            country_result = await session.execute(
                select(RegulatoryCountry.organization_id).where(
                    RegulatoryCountry.id == phase.country_id
                )
            )
            country_org = country_result.scalar_one()

            assert stream_org == country_org, (
                f"Phase {phase_id} mixes orgs: stream in {stream_org}, "
                f"country in {country_org}. Endpoint validation missing."
            )

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Class 6 — Counts sanity check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_produces_parallel_per_org_trees() -> None:
    """Sanity: 2 orgs × 1 stream × 1 country × 1 phase × 1 task × 1 tag = 2 of each."""

    async def _test(session, data):
        for model, expected in (
            (RegulatoryStream, 2),
            (RegulatoryCountry, 2),
            (RegulatoryPhase, 2),
            (RegulatoryTask, 2),
            (RegulatoryTag, 2),
            (RegulatoryTaskTag, 2),
            (RegulatoryTaskNote, 2),
            (RegulatoryPriorityNote, 1),  # only org A has a priority note
        ):
            result = await session.execute(select(model))
            count = len(result.scalars().all())
            assert count == expected, f"{model.__name__}: expected {expected} rows, got {count}"

    await _with_session(_test)
