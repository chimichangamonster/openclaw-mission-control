# ruff: noqa
"""Gateway contract / smoke harness — the OpenClaw upstream-upgrade gate (planning item 141).

WHY THIS EXISTS
---------------
Every other ``test_gateway_*.py`` is MOCKED: it asserts RPC names against MC's own
constant list (``GATEWAY_METHODS``), which is tautological with respect to an upstream
upgrade — the mocks move in lockstep with our assumptions and can never catch a gateway
that reworded an error string or renamed an RPC. This suite is the opposite: it boots a
REAL ``openclaw:local`` container and asserts the MC <-> gateway contract against the
actual running gateway. It converts "MC asserts its own assumptions" into "MC asserts
against the real new gateway."

It is the runbook **Phase 1.5 gate** (``docs/operations/openclaw-gateway-upgrade.md``):
build the candidate image locally, run this suite, green = promote to the VPS canary,
red = the image never reaches production.

WHAT IT PROTECTS (the contract surface a version bump can silently break)
-------------------------------------------------------------------------
1. The connect handshake — PROTOCOL_VERSION=3, the ``connect.challenge`` nonce flow,
   operator-scope negotiation, and ``OPENCLAW_GATEWAY_TOKEN`` auth. (Connects in
   device-pairing mode; production uses control_ui over the docker network, but that needs
   a secure context a docker-published localhost port can't offer — see
   ``_GatewayContainer.config`` for the full rationale. The one documented fidelity gap.)
2. The 3 error strings MC's retry / skip logic sniffs by TEXT — impossible to test with
   mocks, the single most fragile coupling:
     * ``already exists`` (provisioning agents.create idempotency)
     * ``not found``      (provisioning create->update retry + agent delete)
     * ``unsupported file`` (lead-workspace file rejection; ``_NON_TRANSIENT_*`` marker)
   Reword any of these upstream and retry stops firing / loops forever, with NO test
   failure anywhere else.
3. The ~25 consumed RPC methods still exist (rename detection).
4. The cron snake_case -> camelCase round-trip (``app/api/cron_jobs.py`` mapping) survives
   the gateway's jobs.json schema.
5. The ``health`` payload shape (``sessions[].totalTokens`` / ``.model`` / ``.key``) — the
   budget-monitor proactive-compaction lifeline. Drift here SILENTLY degrades UX.
6. ``openclaw.json`` boots without unknown-key rejection (the gateway refuses to start on
   unknown keys — see CLAUDE.md Known Gotchas).

HOW TO RUN
----------
    cd mission-control/backend
    pytest -m gateway_contract -v                 # against openclaw:local
    OPENCLAW_CONTRACT_IMAGE=openclaw:2026.5.2-candidate pytest -m gateway_contract -v

Requirements: a working ``docker`` CLI and the target image present locally. When either
is missing the whole suite SKIPS (so a normal ``make check`` / CI run without the image is
a clean skip, never a failure). Best run under WSL/Linux on Windows — Docker Desktop
bind-mounts (used by the openclaw.json boot test) are native there; see the PowerShell
docker-save gotcha in the runbook.

CALIBRATION NOTE (first-ever run)
---------------------------------
This is the platform's FIRST automated gateway contract suite and the runbook has never
executed end-to-end. The error-string and response-shape assertions below are written from
the verified MC consumer code + production config, but the gateway's EXACT wording / param
requirements are confirmed only by running this against the known-good 2026.2.22 baseline.
The intended workflow (per ``memory/project_gateway_upgrade_strategy.md``): run GREEN
against the 2026.2.22 baseline image to calibrate, THEN trust it as the gate for 2026.5.2.
Where an assertion is lower-confidence it says so inline.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    OpenClawGatewayError,
    openclaw_call,
)

# Every test in this module is an integration test against a real container.
pytestmark = pytest.mark.gateway_contract


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

IMAGE = os.environ.get("OPENCLAW_CONTRACT_IMAGE", "openclaw:local")
# Container-internal gateway port. Production binds 18800 for vantage; the value
# is arbitrary for a throwaway container — we publish it to an ephemeral host port.
CONTAINER_PORT = 18800
# Production parity: `node dist/index.js gateway --allow-unconfigured --bind lan --port N`.
# Image ENTRYPOINT is docker-entrypoint.sh (execs the command array — no doubling),
# WORKDIR /app, User node, so `node dist/index.js ...` resolves correctly.
GATEWAY_BIND = os.environ.get("OPENCLAW_CONTRACT_BIND", "lan")
READY_TIMEOUT_S = 60.0
DOCKER_OP_TIMEOUT_S = 120.0

# Markers the gateway uses to say "I don't know that method." A consumed RPC that
# trips one of these has been RENAMED/REMOVED upstream — the core upgrade risk.
_UNKNOWN_METHOD_MARKERS = (
    "unknown method",
    "method not found",
    "no such method",
    "not a function",
    "unsupported method",
    "unknown rpc",
    "unhandled method",
)


# ---------------------------------------------------------------------------
# Container management (docker CLI via subprocess — zero new dependencies)
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, timeout: float = DOCKER_OP_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _require_docker_and_image() -> None:
    """Skip the whole suite cleanly when docker or the target image is absent."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not on PATH — gateway contract suite requires Docker")
    inspect = _run(["docker", "image", "inspect", IMAGE], timeout=30)
    if inspect.returncode != 0:
        pytest.skip(
            f"image {IMAGE!r} not present locally — build it (runbook Phase 1) or set "
            f"OPENCLAW_CONTRACT_IMAGE. `docker image inspect` said: "
            f"{inspect.stderr.strip() or 'not found'}"
        )


@pytest.fixture(scope="module", autouse=True)
def _isolated_device_identity() -> None:
    """Point device-identity creation at a throwaway path for the whole module.

    Device-pairing mode (see ``_GatewayContainer.config``) persists an ed25519 keypair via
    ``load_or_create_device_identity()``; without this it would read/write the developer's
    real ``~/.openclaw/identity/device.json``. Isolate it so the harness leaves no trace.
    """
    previous = os.environ.get("OPENCLAW_GATEWAY_DEVICE_IDENTITY_PATH")
    with tempfile.TemporaryDirectory(prefix="vc-gw-contract-id-") as tmp:
        os.environ["OPENCLAW_GATEWAY_DEVICE_IDENTITY_PATH"] = str(Path(tmp) / "device.json")
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("OPENCLAW_GATEWAY_DEVICE_IDENTITY_PATH", None)
            else:
                os.environ["OPENCLAW_GATEWAY_DEVICE_IDENTITY_PATH"] = previous


class _GatewayContainer:
    """A throwaway ``openclaw:local`` gateway booted for one test module.

    Connects exactly the way production does: control_ui mode
    (``disable_device_pairing=true``) authenticated by ``OPENCLAW_GATEWAY_TOKEN``.
    """

    def __init__(
        self,
        *,
        image: str = IMAGE,
        token: str | None = None,
        extra_env: dict[str, str] | None = None,
        host_openclaw_dir: str | None = None,
    ) -> None:
        self.image = image
        self.token = token or secrets.token_hex(24)
        self.extra_env = extra_env or {}
        self.host_openclaw_dir = host_openclaw_dir
        self.name = f"vc-gw-contract-{uuid4().hex[:12]}"
        self._started = False

    def start(self) -> None:
        cmd = [
            "docker", "run", "-d",
            "--name", self.name,
            "--init",
            "-e", "HOME=/home/node",
            "-e", f"OPENCLAW_GATEWAY_TOKEN={self.token}",
        ]
        for key, value in self.extra_env.items():
            cmd += ["-e", f"{key}={value}"]
        if self.host_openclaw_dir is not None:
            # Bind the whole .openclaw dir (matches production); more reliable than a
            # single-file mount on Docker Desktop. Requires the drive to be file-shared.
            cmd += ["-v", f"{self.host_openclaw_dir}:/home/node/.openclaw"]
        # Publish the gateway port to an ephemeral host port on loopback.
        cmd += ["-p", f"127.0.0.1::{CONTAINER_PORT}"]
        cmd += [
            self.image,
            "node", "dist/index.js", "gateway",
            "--allow-unconfigured",
            "--bind", GATEWAY_BIND,
            "--port", str(CONTAINER_PORT),
        ]
        result = _run(cmd)
        if result.returncode != 0:
            raise RuntimeError(
                f"failed to start gateway container: {result.stderr.strip() or result.stdout.strip()}"
            )
        self._started = True

    def published_port(self) -> int:
        result = _run(["docker", "port", self.name, str(CONTAINER_PORT)], timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"`docker port` failed: {result.stderr.strip()}")
        # Output like "127.0.0.1:55001" (possibly multiple lines for v4/v6).
        for line in result.stdout.splitlines():
            line = line.strip()
            if ":" in line:
                return int(line.rsplit(":", 1)[1])
        raise RuntimeError(f"could not parse published port from: {result.stdout!r}")

    def config(self) -> GatewayConfig:
        port = self.published_port()
        return GatewayConfig(
            url=f"ws://127.0.0.1:{port}",
            token=self.token,
            # Device-pairing mode (ed25519 + token), NOT control_ui. Production connects in
            # control_ui mode (disable_device_pairing=true) over the docker network, but the
            # gateway rejects control_ui over a docker-PUBLISHED localhost port —
            # "control ui requires device identity (use HTTPS or localhost secure context)" —
            # because NAT makes the connection look non-local. Device mode exercises the same
            # PROTOCOL_VERSION negotiation, connect.challenge nonce, and operator-scope
            # handshake, and EVERY downstream RPC / error-string / event shape is connect-mode
            # independent. The connect-mode difference is the one documented fidelity gap of a
            # localhost harness (verified against the 2026.2.22 baseline 2026-06-03).
            disable_device_pairing=False,
            allow_insecure_tls=False,
        )

    def logs(self, tail: int = 80) -> str:
        if not self._started:
            return "(container never started)"
        result = _run(["docker", "logs", "--tail", str(tail), self.name], timeout=30)
        return (result.stdout + result.stderr).strip()

    def stop(self) -> None:
        if self._started:
            _run(["docker", "rm", "-f", self.name], timeout=60)
            self._started = False


def _wait_ready(container: _GatewayContainer) -> GatewayConfig:
    """Poll the gateway with the real ``health`` RPC until it answers (or fail loudly)."""
    deadline = time.monotonic() + READY_TIMEOUT_S
    last_error: str = "(no attempt completed)"
    config = container.config()
    while time.monotonic() < deadline:
        try:
            asyncio.run(openclaw_call("health", config=config))
            return config
        except Exception as exc:  # noqa: BLE001 — readiness probe, any failure = retry
            last_error = f"{exc.__class__.__name__}: {exc}"
            time.sleep(1.0)
    raise RuntimeError(
        f"gateway never became ready within {READY_TIMEOUT_S:.0f}s. "
        f"Last probe error: {last_error}\n--- container logs ---\n{container.logs()}"
    )


@dataclass
class _GatewayHarness:
    config: GatewayConfig
    container: _GatewayContainer


@pytest.fixture(scope="module")
def gateway() -> _GatewayHarness:
    """Boot one ``openclaw:local`` gateway for the whole module.

    Contract: tests sharing this fixture MUST NOT issue an RPC that triggers a gateway
    "config change requires restart". A successful agents.create — and equally config.patch
    (the co-trigger production uses in patch_agent_heartbeats) — fires a SIGUSR1 full-process
    restart that takes the WS listener down for ~19s and destabilizes every subsequent test
    (verified 2026-06-03). Tests that need such a mutation use the function-scoped
    ``fresh_gateway`` fixture instead. Safe on this fixture: read-only calls, bogus-target
    calls (which error without mutating), agents.files.set on the pre-existing ``main`` agent
    (does NOT restart), and cron add/remove (does NOT restart).
    """
    _require_docker_and_image()
    container = _GatewayContainer()
    container.start()
    try:
        config = _wait_ready(container)
        yield _GatewayHarness(config=config, container=container)
    finally:
        container.stop()


@pytest.fixture
def fresh_gateway() -> _GatewayHarness:
    """A dedicated single-use gateway for a test that performs a real agent mutation.

    A successful agents.create triggers a debounced hot-reload that drops the WS listener
    for ~19s. Isolating such a test in its own throwaway container keeps that reload from
    destabilizing the shared module ``gateway``.
    """
    _require_docker_and_image()
    container = _GatewayContainer()
    container.start()
    try:
        config = _wait_ready(container)
        yield _GatewayHarness(config=config, container=container)
    finally:
        container.stop()


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------


# Transient connect/transport errors that MC itself retries (see constants.py
# _TRANSIENT_GATEWAY_ERROR_MARKERS). A fresh WS connect to a busy gateway occasionally
# gets "did not receive a valid HTTP response" (websockets InvalidMessage); retry so the
# gate is deterministic, exactly as production does.
_TRANSIENT_MARKERS = (
    "did not receive a valid http response",
    "refused",  # "connection refused" (POSIX) + "refused the network connection" (WinError 1225)
    "1225",  # WinError 1225
    "actively refused",  # WinError 10061 phrasing
    "connection reset",
    "connection closed",
    "reset by peer",
    "broken pipe",
    "timed out",
    "timeout",
    "econnrefused",
    "received 1012",
    "service restart",
)


async def _robust_call(
    harness: _GatewayHarness,
    method: str,
    params: dict | None = None,
    *,
    attempts: int = 20,
    delay: float = 1.5,
) -> object:
    """Call an RPC, retrying only on transient transport errors. Non-transient gateway
    errors (not found / already exists / unsupported file / validation) raise immediately.

    The retry window (~30s) generously absorbs connection refusals while the gateway's WS
    listener is briefly down: a successful agents.create (or config.patch) triggers a
    SIGUSR1 full-process restart that re-inits the listener for ~19s (verified 2026-06-03),
    and the docker-proxy occasionally throws "did not receive a valid HTTP response" /
    WinError 1225 under load.

    This does not mask a contract regression PROVIDED the gateway delivers method/schema
    errors as a `res ok:false` envelope (the 2026.2.22 behavior): those reach the caller as
    a gateway error string and are never retried. The one residual hole — a future gateway
    that signals a renamed/removed RPC by CLOSING the websocket (a ConnectionClosed whose
    message matches a transient marker) — is closed at the assertion layer: `_assert_recognized`
    fails on a terminal transient/transport error rather than treating it as recognized.
    """
    last_exc: OpenClawGatewayError | None = None
    for attempt in range(attempts):
        try:
            return await openclaw_call(method, params, config=harness.config)
        except OpenClawGatewayError as exc:
            last_exc = exc
            transient = any(m in str(exc).lower() for m in _TRANSIENT_MARKERS)
            if transient and attempt < attempts - 1:
                await asyncio.sleep(delay)
                continue
            raise
    assert last_exc is not None  # unreachable
    raise last_exc


async def _call_capture(
    harness: _GatewayHarness,
    method: str,
    params: dict | None = None,
) -> tuple[object | None, str | None]:
    """Call an RPC; return (result, None) on success or (None, error_message) on gateway error."""
    try:
        result = await _robust_call(harness, method, params)
        return result, None
    except OpenClawGatewayError as exc:
        return None, str(exc)


def _is_unknown_method_error(message: str | None) -> bool:
    if not message:
        return False
    low = message.lower()
    return any(marker in low for marker in _UNKNOWN_METHOD_MARKERS)


def _is_transient_error(message: str | None) -> bool:
    if not message:
        return False
    low = message.lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


def _assert_recognized(method: str, result: object | None, error: str | None) -> None:
    """A method is 'recognized' if it succeeds OR returns a gateway-level error for any
    reason OTHER than 'unknown method'. A param/validation/not-found gateway error still
    proves the RPC exists — only an unknown-method error means it was renamed or removed.

    Crucially we ALSO fail on a terminal transport/transient error: if a swept call yields
    only a connection-close / refusal after _robust_call exhausted its ~30s retry window
    (the module container is mutation-free and stable, so that shouldn't happen), we cannot
    confirm the method is recognized — and a future gateway that answers a renamed RPC by
    CLOSING the websocket (rather than a `res ok:false`) would otherwise be silently passed
    as 'recognized'. Treat that as a hard failure, not a pass.
    """
    assert not _is_unknown_method_error(error), (
        f"RPC {method!r} appears RENAMED/REMOVED upstream — gateway returned an "
        f"unknown-method error: {error!r}. Every MC consumer of this method is now broken."
    )
    assert not _is_transient_error(error), (
        f"RPC {method!r} produced only a transport/connection error after retries "
        f"({error!r}) — cannot confirm it is recognized. A gateway that answers an "
        f"unknown method by closing the websocket would land here; investigate before "
        f"trusting this as a pass."
    )


# ---------------------------------------------------------------------------
# Tier 1 — connect handshake + the 3 fragile error strings (the priority)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_connect_handshake_and_health(gateway: _GatewayHarness) -> None:
    """The full control_ui + token handshake (PROTOCOL_VERSION, connect.challenge nonce,
    auth) must complete and `health` must answer with a dict payload.
    """
    payload = await _robust_call(gateway, "health")
    assert isinstance(payload, dict), f"health returned {type(payload).__name__}, expected dict"


@pytest.mark.asyncio(loop_scope="module")
async def test_error_string_already_exists(fresh_gateway: _GatewayHarness) -> None:
    """Creating the same agent twice must surface an 'already exists'-class error.

    ``provisioning.py`` swallows agents.create when the message contains any of
    {already, exist, duplicate, conflict}; reword these upstream and create stops being
    idempotent. (High confidence — verified live: "agent \\"X\\" already exists".)

    Uses ``fresh_gateway`` because the first (successful) create triggers a ~19s hot-reload.
    The duplicate create rides out that reload via ``_robust_call``'s retry, then surfaces
    the non-transient 'already exists'. No cleanup needed — the container is thrown away.
    """
    agent_id = f"contract-dup-{uuid4().hex[:8]}"
    # agents.create is keyed by `name` (the name IS the agentId); it rejects an `agentId`
    # property at root. Verified against the 2026.2.22 baseline 2026-06-03.
    create_params = {
        "name": agent_id,
        "workspace": f"/home/node/.openclaw/agents/{agent_id}",
    }
    _first, first_err = await _call_capture(fresh_gateway, "agents.create", create_params)
    assert first_err is None, (
        f"first agents.create unexpectedly failed: {first_err!r} — "
        f"adjust create params to match the gateway's required shape"
    )
    _result, dup_err = await _call_capture(fresh_gateway, "agents.create", create_params)
    assert dup_err is not None, "duplicate agents.create did NOT error — idempotency contract broke"
    low = dup_err.lower()
    assert any(m in low for m in ("already", "exist", "duplicate", "conflict")), (
        f"duplicate-create error string drifted away from MC's markers "
        f"{{already, exist, duplicate, conflict}}: {dup_err!r}"
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_error_string_agent_not_found(gateway: _GatewayHarness) -> None:
    """agents.update on a non-existent agent must surface 'agent ... not found'.

    ``provisioning.py`` create->update retry and ``admin_service`` delete both key on this
    text via ``_is_missing_agent_error``: matches {unknown agent, no such agent,
    agent does not exist} OR ('agent' AND 'not found'). (High confidence.)
    """
    missing = f"contract-missing-{uuid4().hex[:8]}"
    _result, err = await _call_capture(
        gateway,
        "agents.update",
        {"agentId": missing, "name": missing, "workspace": f"/home/node/.openclaw/agents/{missing}"},
    )
    assert err is not None, "agents.update on a missing agent did NOT error"
    low = err.lower()
    matched = ("agent" in low and "not found" in low) or any(
        m in low for m in ("unknown agent", "no such agent", "agent does not exist")
    )
    assert matched, (
        f"missing-agent error string drifted away from MC's _is_missing_agent_error "
        f"markers — provisioning create->update retry keys on this: {err!r}"
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_error_string_unsupported_file(gateway: _GatewayHarness) -> None:
    """agents.files.set with a disallowed filename must surface 'unsupported file'.

    ``constants._NON_TRANSIENT_GATEWAY_ERROR_MARKERS`` + ``provisioning.py`` classify this
    as NON-transient; reword it and a permanent rejection gets retried forever as if it
    were a transient network blip. The gateway allowlists agent files (SOUL.md, TOOLS.md,
    AGENTS.md, ...); a name outside the allowlist trips the rejection.
    (Medium-high confidence — depends on the gateway enforcing the allowlist + wording.)
    """
    # Target the pre-existing default agent ``main`` so we trigger the FILENAME check
    # without a successful agent mutation (which would bounce the listener). The gateway
    # validates agent-existence first (a bogus agentId returns "unknown agent id"), so the
    # agent must really exist for the filename rejection to fire. Verified live 2026-06-03:
    # files.set on "main" with a disallowed name -> 'unsupported file "BAD.exe"'.
    _result, err = await _call_capture(
        gateway,
        "agents.files.set",
        {"agentId": "main", "name": "NOT_AN_ALLOWED_FILE.exe", "content": "x"},
    )
    assert err is not None, "agents.files.set with a disallowed name did NOT error"
    assert "unsupported file" in err.lower(), (
        f"unsupported-file error string drifted from MC's non-transient marker — a "
        f"permanent rejection will now be retried as transient: {err!r}"
    )


# ---------------------------------------------------------------------------
# Tier 2 — the ~25 consumed RPC methods still exist (rename detection)
# ---------------------------------------------------------------------------

# (method, params) chosen so each call is recognized without side effects we can't undo.
# Bogus ids / keys make mutating methods return a clean "not found" (= recognized) without
# actually mutating anything. The real round-trips for cron + agents + sessions get their
# own dedicated tests below.
_RECOGNITION_SWEEP: list[tuple[str, dict | None]] = [
    ("health", None),
    ("status", None),
    ("config.get", None),
    ("models.list", None),
    ("agents.list", None),
    ("sessions.list", None),
    ("cron.list", None),
    ("cron.status", None),
    ("chat.history", {"sessionKey": "contract:nonexistent:session"}),
    ("chat.abort", {"sessionKey": "contract:nonexistent:session"}),
    ("sessions.preview", {"key": "contract:nonexistent:session"}),
    ("sessions.compact", {"key": "contract:nonexistent:session"}),
    ("sessions.reset", {"key": "contract:nonexistent:session"}),
    ("sessions.delete", {"key": "contract:nonexistent:session"}),
    ("agents.update", {"agentId": "contract-nope", "name": "x", "workspace": "/tmp/x"}),
    ("agents.delete", {"agentId": "contract-nope"}),
    ("agents.files.list", {"agentId": "contract-nope"}),
    ("agents.files.get", {"agentId": "contract-nope", "name": "SOUL.md"}),
    ("cron.update", {"id": "contract-nope"}),
    ("cron.remove", {"id": "contract-nope"}),
    ("cron.run", {"id": "contract-nope"}),
    ("cron.runs", {"id": "contract-nope"}),
]


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(("method", "params"), _RECOGNITION_SWEEP, ids=[m for m, _ in _RECOGNITION_SWEEP])
async def test_consumed_rpc_method_is_recognized(
    gateway: _GatewayHarness, method: str, params: dict | None
) -> None:
    """Each consumed RPC must still be a known method (catches upstream renames)."""
    result, error = await _call_capture(gateway, method, params)
    _assert_recognized(method, result, error)


# ---------------------------------------------------------------------------
# Tier 2 — deeper round-trips for the highest-traffic surfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_cron_snake_to_camel_roundtrip(gateway: _GatewayHarness) -> None:
    """The ``app/api/cron_jobs.py`` snake_case -> camelCase mapping must survive the
    gateway's jobs.json schema.

    cron.add echoes back the parsed/normalized job object, so we assert the round-trip
    against the add RESPONSE — write camelCase in, get the same camelCase keys back. The
    asserted keys are the ones ``_normalize_job()`` reads (agentId / schedule.{kind,expr,tz}
    / sessionTarget / payload.message / delivery.mode); rename any of them upstream and the
    cron-jobs UI silently shows blanks.

    Fidelity caveat: production reads only ``id`` from the cron.add response and runs
    ``_normalize_job`` over the cron.LIST / jobs.json shape, so the add-echo is a PROXY for
    the stored shape, not literally it. We assert the echo because cron.list legitimately
    returns [] here (bare --allow-unconfigured gateway, no live agent runtime — runtime
    scoping, not a schema break; verified 2026-06-03). If the gateway ever lets the add-echo
    and the stored cron.list shape diverge on a key rename, this would pass while the UI
    blanks — caught by the runbook Phase 3.3 canary smoke (real cron list in the UI).
    """
    # Exactly the shape _build_add_params() emits for a CronJobCreate.
    add_params = {
        "name": f"contract-cron-{uuid4().hex[:8]}",
        "agentId": "contract-agent",
        "enabled": False,
        "schedule": {"kind": "cron", "expr": "0 9 * * 1", "tz": "America/Edmonton"},
        "payload": {"message": "contract round-trip probe", "timeoutSeconds": 30},
        "sessionTarget": "isolated",
        "delivery": {"mode": "none"},
        "description": "gateway-contract-harness test job",
    }
    job, add_err = await _call_capture(gateway, "cron.add", add_params)
    assert add_err is None, f"cron.add failed: {add_err!r}"
    assert isinstance(job, dict), f"cron.add returned {type(job).__name__}, expected dict"
    job_id = job.get("id")
    assert isinstance(job_id, str) and job_id, f"cron.add did not return an id: {job!r}"

    try:
        # Every key on the right is one _normalize_job() reads back.
        assert job.get("agentId") == "contract-agent", f"agentId round-trip lost: {job!r}"
        assert job.get("sessionTarget") == "isolated", f"sessionTarget round-trip lost: {job!r}"
        schedule = job.get("schedule") or {}
        assert schedule.get("kind") == "cron", f"schedule.kind round-trip lost: {schedule!r}"
        assert schedule.get("expr") == "0 9 * * 1", f"schedule.expr round-trip lost: {schedule!r}"
        assert schedule.get("tz") == "America/Edmonton", f"schedule.tz round-trip lost: {schedule!r}"
        payload = job.get("payload") or {}
        assert payload.get("message") == "contract round-trip probe", (
            f"payload.message round-trip lost: {payload!r}"
        )
        delivery = job.get("delivery") or {}
        assert delivery.get("mode") == "none", (
            f"delivery.mode round-trip broke (got {delivery!r}) — note 'silent' silently "
            f"coerces to 'announce' (see CLAUDE.md cron gotcha)"
        )
    finally:
        await _call_capture(gateway, "cron.remove", {"id": job_id})


@pytest.mark.asyncio(loop_scope="module")
async def test_health_payload_shape(gateway: _GatewayHarness) -> None:
    """The ``health`` RPC payload shape that MC's gateway-health surfaces consume.

    The health RPC returns ``{ok, ts, ..., agents, sessions}`` where ``sessions`` is a
    SUMMARY object ``{path, count, recent}`` (verified against the 2026.2.22 baseline
    2026-06-03). Note this differs from the health EVENT payload, whose ``sessions`` is a
    per-session list carrying ``totalTokens`` / ``model`` / ``key`` — the budget-monitor
    proactive-compaction lifeline that ``_diff_health_sessions`` reads. That event shape
    needs a live agent turn and is covered by the LLM-gated Tier 3 test below.
    """
    payload = await _robust_call(gateway, "health")
    assert isinstance(payload, dict), f"health returned {type(payload).__name__}, expected dict"
    assert payload.get("ok") is True, f"health.ok not True: {payload.get('ok')!r}"
    assert "agents" in payload, f"health payload lost 'agents': keys={sorted(payload)}"

    sessions = payload.get("sessions")
    assert isinstance(sessions, dict), (
        f"health.sessions changed shape — expected summary dict {{path,count,recent}}, "
        f"got {type(sessions).__name__}: {sessions!r}"
    )
    assert "count" in sessions, f"health.sessions lost 'count': {sessions!r}"
    assert "recent" in sessions and isinstance(sessions["recent"], list), (
        f"health.sessions lost 'recent' list: {sessions!r}"
    )


# ---------------------------------------------------------------------------
# Tier 2 — openclaw.json boots without unknown-key rejection
# ---------------------------------------------------------------------------

# The gateway runs its config "doctor" at boot and flags unrecognized keys ("Unknown
# config keys" / "Config invalid"; on stricter versions it can refuse to start — CLAUDE.md
# Known Gotchas). This boots a dedicated gateway with a mounted openclaw.json containing the
# `env` block MC's template writes and asserts (a) the gateway reaches steady state and
# (b) the boot logs report NO unknown/invalid config. If upstream renames/removes a key we
# write, the doctor flags it and this fails.
#
# Scoped to the `env` key for now: a fully-valid representative config is version-specific
# (e.g. 2026.2.22 rejects arbitrary `agents.<name>` keys via openclaw.json), so broader
# key coverage (agents.* / compaction.mode) is deferred to calibration against a real
# production config snapshot. Verified `env`-only is clean on 2026.2.22 (2026-06-03).
_REPRESENTATIVE_OPENCLAW_JSON = {
    "env": {"OPENROUTER_API_KEY": "sk-contract-placeholder"},
}
_CONFIG_REJECTION_MARKERS = ("unknown config keys", "config invalid", "unrecognized key")


def test_openclaw_json_boots_without_unknown_key_rejection() -> None:
    """A representative openclaw.json must boot clean — no unknown-key / invalid-config flags.

    Synchronous on purpose: it drives the sync ``_wait_ready`` probe (which uses
    ``asyncio.run``) and must not run inside an event loop.
    """
    _require_docker_and_image()
    with tempfile.TemporaryDirectory(prefix="vc-gw-contract-cfg-") as tmp:
        cfg_dir = Path(tmp)
        (cfg_dir / "openclaw.json").write_text(
            json.dumps(_REPRESENTATIVE_OPENCLAW_JSON, indent=2), encoding="utf-8"
        )
        container = _GatewayContainer(host_openclaw_dir=str(cfg_dir))
        try:
            container.start()
        except RuntimeError as exc:
            # Most likely a Docker Desktop bind-mount / drive-sharing issue on this host —
            # don't fail the gate for an environment quirk; calibrate under WSL/Linux.
            pytest.skip(f"could not bind-mount config dir (host/Docker setup): {exc}")
        try:
            _wait_ready(container)
            logs_low = container.logs(tail=200).lower()
            flagged = [m for m in _CONFIG_REJECTION_MARKERS if m in logs_low]
            assert not flagged, (
                f"gateway flagged our openclaw.json at boot ({flagged}) — a key MC's "
                f"template writes is no longer recognized upstream. Boot logs:\n"
                f"{container.logs(tail=200)}"
            )
        finally:
            container.stop()


# ---------------------------------------------------------------------------
# Tier 2 — production's control_ui + token connect path (item-98 pre-flight)
# ---------------------------------------------------------------------------

# Production connects in control_ui mode (disable_device_pairing=true) + token, NOT the
# device-pairing mode the module `gateway` fixture uses. A bare gateway rejects control_ui
# over a docker-published port ("control ui requires device identity ...") because it isn't
# a local/secure context; production allows it via this gateway config block (verified
# against the live vantage openclaw.json 2026-06-03). This test boots a gateway WITH that
# block and asserts MC's REAL control_ui connect path is accepted — closing the connect-mode
# fidelity gap. It matters specifically for the 2026.2.22->2026.5.2 upgrade: upstream is
# actively reworking the control_ui device-pairing-skip path across that delta
# (changelog #25428 / #30740 / #69431), and the device-pairing test would not catch a
# regression in it.
_CONTROL_UI_OPENCLAW_JSON = {
    "env": {"OPENROUTER_API_KEY": "sk-contract-placeholder"},
    "gateway": {
        "controlUi": {"allowInsecureAuth": True, "dangerouslyDisableDeviceAuth": True},
    },
}


def test_control_ui_token_connect_path() -> None:
    """MC's production connect path — control_ui (disable_device_pairing=True) + token —
    must be accepted by a gateway carrying the production ``gateway.controlUi`` config.

    Synchronous on purpose (drives an ``asyncio.run`` readiness probe). Fails hard if the
    gateway answers the control_ui handshake with a device-identity / pairing rejection —
    that means the upstream control_ui auth path the platform depends on has regressed.
    """
    _require_docker_and_image()
    with tempfile.TemporaryDirectory(prefix="vc-gw-contract-cui-") as tmp:
        cfg_dir = Path(tmp)
        (cfg_dir / "openclaw.json").write_text(
            json.dumps(_CONTROL_UI_OPENCLAW_JSON, indent=2), encoding="utf-8"
        )
        container = _GatewayContainer(host_openclaw_dir=str(cfg_dir))
        try:
            container.start()
        except RuntimeError as exc:
            pytest.skip(f"could not bind-mount controlUi config (host/Docker setup): {exc}")
        try:
            port = container.published_port()
            # The production connect mode: control_ui + token (NOT device-pairing).
            cui = GatewayConfig(
                url=f"ws://127.0.0.1:{port}",
                token=container.token,
                disable_device_pairing=True,
                allow_insecure_tls=False,
            )

            async def _probe() -> object:
                deadline = time.monotonic() + READY_TIMEOUT_S
                last = "(no attempt completed)"
                while time.monotonic() < deadline:
                    try:
                        return await openclaw_call("health", config=cui)
                    except OpenClawGatewayError as exc:
                        msg = str(exc).lower()
                        # A device-identity / pairing rejection is the contract failure this
                        # test exists to catch — fail hard, do NOT retry it as a boot blip.
                        if "device identity" in msg or "pairing" in msg:
                            raise AssertionError(
                                "control_ui + token connect was REJECTED "
                                f"({exc!r}) — production's connect/auth path has regressed. "
                                "gateway.controlUi.allowInsecureAuth / dangerouslyDisableDeviceAuth "
                                "may no longer be honored upstream."
                            ) from exc
                        # Anything else (boot not finished, transport blip) — keep polling.
                        last = str(exc)
                        await asyncio.sleep(1.0)
                msg = (
                    f"gateway never accepted control_ui within {READY_TIMEOUT_S:.0f}s. "
                    f"Last error: {last}\n--- container logs ---\n{container.logs()}"
                )
                raise RuntimeError(msg)

            payload = asyncio.run(_probe())
            assert isinstance(payload, dict), f"health returned {type(payload).__name__}"
            assert payload.get("ok") is True, f"control_ui health.ok not True: {payload!r}"
        finally:
            container.stop()


# ---------------------------------------------------------------------------
# Tier 3 — live chat round-trip + chat/health EVENT shapes (LLM-gated, opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_chat_final_and_health_event_shapes() -> None:
    """End-to-end chat turn → assert the `chat` final event + `health` event wire shapes.

    These are the shapes ``gateway_event_listener._normalise_event`` /
    ``_diff_health_sessions`` consume (``chat.state`` / ``chat.sessionKey`` /
    ``chat.message``; ``health.sessions[].totalTokens``). Asserting them requires a LIVE
    LLM turn (real OpenRouter spend + latency + flakiness), so this is OPT-IN: set
    ``OPENCLAW_CONTRACT_LLM=1`` and provide ``OPENROUTER_API_KEY``.

    DEFERRED for first-run calibration: the deterministic Tier 1/2 tests are the gate;
    the live chat round-trip is also covered by the runbook's Phase 3.3 manual canary
    smoke ("send 'ping' in #general, agent replies"). Wire the full listener assertion
    here once the suite is green against the 2026.2.22 baseline.
    """
    if os.environ.get("OPENCLAW_CONTRACT_LLM") != "1":
        pytest.skip("set OPENCLAW_CONTRACT_LLM=1 (+ OPENROUTER_API_KEY) to run the live-LLM event-shape test")
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set — required for the live-LLM event-shape test")
    pytest.skip(
        "live-LLM event-shape assertion not yet wired — covered by runbook Phase 3.3 "
        "canary smoke; implement against the green 2026.2.22 baseline (see module docstring)"
    )
