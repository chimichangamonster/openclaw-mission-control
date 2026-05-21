"""SSRF + DNS-rebinding defense for partner webhook URLs.

See `docs/business/partner-api-v1-scope.md` (Webhook security → URL validation
+ DNS-rebinding defense) for the strict policy this enforces.

Two entry points serve two phases of the lifecycle:

* :func:`validate_webhook_url_at_create_time` runs in the POST handler. Parses
  the URL, enforces HTTPS, resolves the hostname, and rejects any forbidden
  range (loopback, RFC1918, link-local, CGNAT/Tailscale, ``.internal`` etc.).
* :func:`validate_resolved_host` runs in the dispatcher right before the HTTP
  request fires. The dispatcher re-resolves the hostname and feeds the
  resolved address(es) here — an attacker who registered a public hostname
  at create time can rebind to private space later, and this catches it.

Both share :func:`_is_forbidden_ip` so the policy lives in one place.

The policy is intentionally strict per the private-PaaS-for-select-partners
posture: partners with on-prem-only networks are handled as direct
conversations, not by relaxing the public default.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Hostname suffixes that must never resolve a partner webhook. These cover
# the common internal-DNS conventions plus literal ``localhost``.
FORBIDDEN_HOST_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
)

FORBIDDEN_HOSTS: frozenset[str] = frozenset(
    {
        "localhost",
    }
)

# Maximum URL length. Loosely chosen — most browsers cap around 2048; we
# allow more for unusual partner endpoints but reject obvious abuse.
MAX_URL_LENGTH = 2048


class WebhookUrlValidationError(ValueError):
    """Raised when a webhook URL fails SSRF/DNS-rebinding policy."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _is_forbidden_ip(addr: str) -> bool:
    """True if ``addr`` (string IP) is in any forbidden range.

    Covers:

    * Loopback (``127.0.0.0/8``, ``::1``)
    * RFC1918 private (``10/8``, ``172.16/12``, ``192.168/16``)
    * Link-local (``169.254.0.0/16``, ``fe80::/10``)
    * CGNAT (``100.64.0.0/10``) — also covers Tailscale tailnet IPv4 range
    * Tailscale IPv6 ULA (``fd7a:115c:a1e0::/48``)
    * Unspecified / multicast / reserved
    """
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Caller fed us a non-IP; treat as forbidden so the create path
        # doesn't accidentally pass through a junk value.
        return True

    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True

    # CGNAT 100.64.0.0/10 is NOT flagged by ``is_private`` on Python 3.12,
    # but it's where Tailscale tailnet IPv4 addresses live — and any public
    # CGNAT-allocated address is also off-limits for a public webhook
    # target. Check explicitly.
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    if isinstance(ip, ipaddress.IPv4Address) and ip in cgnat:
        return True

    # Tailscale IPv6 ULA range.
    tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
    if isinstance(ip, ipaddress.IPv6Address) and ip in tailscale_v6:
        return True

    return False


def _is_forbidden_hostname(hostname: str) -> bool:
    """True if ``hostname`` matches a forbidden literal or suffix."""
    host = hostname.lower()
    if host in FORBIDDEN_HOSTS:
        return True
    for suffix in FORBIDDEN_HOST_SUFFIXES:
        if host.endswith(suffix):
            return True
    return False


def _resolve_all(hostname: str) -> list[str]:
    """Resolve ``hostname`` to every IP address it currently maps to.

    Returns all unique address strings across IPv4 + IPv6 records. Raises
    ``WebhookUrlValidationError`` on DNS failure since an unresolvable
    hostname is unusable as a webhook target anyway.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookUrlValidationError(
            f"hostname does not resolve: {hostname}"
        ) from exc
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        # IPv4 sockaddr is (host, port); IPv6 is (host, port, flowinfo, scope).
        if isinstance(sockaddr, tuple) and len(sockaddr) >= 1:
            seen.add(str(sockaddr[0]))
    return sorted(seen)


def validate_webhook_url_at_create_time(url: str) -> None:
    """Enforce SSRF policy at subscription create time.

    Raises :class:`WebhookUrlValidationError` on any policy violation. The
    caller (POST handler) translates that to a 422.
    """
    if not url or not isinstance(url, str):
        raise WebhookUrlValidationError("url must be a non-empty string")
    if len(url) > MAX_URL_LENGTH:
        raise WebhookUrlValidationError(
            f"url exceeds maximum length of {MAX_URL_LENGTH} characters"
        )

    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise WebhookUrlValidationError("url must use https:// scheme")
    if not parsed.hostname:
        raise WebhookUrlValidationError("url must include a hostname")
    if parsed.username or parsed.password:
        raise WebhookUrlValidationError("url must not embed userinfo")

    hostname = parsed.hostname
    if _is_forbidden_hostname(hostname):
        raise WebhookUrlValidationError(
            f"hostname matches forbidden internal pattern: {hostname}"
        )

    # If the hostname IS a literal IP, check that directly without DNS.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_forbidden_ip(str(literal)):
            raise WebhookUrlValidationError(
                f"url resolves to forbidden address range: {literal}"
            )
        return

    # Otherwise resolve and check every returned address.
    addresses = _resolve_all(hostname)
    if not addresses:
        raise WebhookUrlValidationError(f"hostname does not resolve: {hostname}")
    for addr in addresses:
        if _is_forbidden_ip(addr):
            raise WebhookUrlValidationError(
                f"hostname {hostname} resolved to forbidden address {addr}"
            )


def validate_resolved_host(hostname: str) -> None:
    """Dispatch-time DNS-rebinding defense.

    The dispatcher calls this right before firing — re-resolves the
    hostname and ensures it still points only to public addresses. An
    attacker who registers ``attacker.example.com`` (public at create
    time) and later rebinds it to ``192.168.x.x`` is caught here.

    Raises :class:`WebhookUrlValidationError` if any current resolution
    is in a forbidden range. The dispatcher logs the rejection to the
    failures-audit table with ``reason: "dns_resolved_to_private"``.
    """
    if _is_forbidden_hostname(hostname):
        raise WebhookUrlValidationError(
            f"hostname matches forbidden internal pattern: {hostname}"
        )

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_forbidden_ip(str(literal)):
            raise WebhookUrlValidationError(
                f"hostname resolves to forbidden address: {literal}"
            )
        return

    addresses = _resolve_all(hostname)
    for addr in addresses:
        if _is_forbidden_ip(addr):
            raise WebhookUrlValidationError(
                f"hostname {hostname} now resolves to forbidden address {addr}"
            )
