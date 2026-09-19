"""Trusted proxy handling for client IP resolution (correction pass item 6).

Rules under test:

* a direct client cannot spoof its address by sending ``X-Forwarded-For``;
* when the direct peer *is* a configured trusted proxy, the original client is
  taken from the forwarded chain, skipping the proxies in between;
* the resolved address is what audit records and rate limiting use.
"""

from __future__ import annotations

from ipaddress import ip_network

from sqlalchemy import select

from app.auth.dependencies import resolve_client_ip
from app.core.config import settings
from app.models.audit import AuditLog
from tests.conftest import OWNER_EMAIL, create_user

TRUSTED = [ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12")]


def test_direct_client_cannot_spoof_x_forwarded_for() -> None:
    resolved = resolve_client_ip("203.0.113.50", "1.2.3.4, 5.6.7.8", trusted_networks=[])
    assert resolved == "203.0.113.50"


def test_trusted_proxy_resolves_the_original_client() -> None:
    assert resolve_client_ip("10.1.2.3", "203.0.113.9", TRUSTED) == "203.0.113.9"


def test_chain_skips_trusted_hops() -> None:
    # client -> proxy A (trusted) -> proxy B (trusted) -> us
    resolved = resolve_client_ip("10.0.0.9", "198.51.100.7, 172.16.5.4", TRUSTED)
    assert resolved == "198.51.100.7"


def test_client_behind_two_proxies_with_spoofed_prefix() -> None:
    # The client appended a fake entry; walking right-to-left still finds the real
    # client (the right-most untrusted hop) instead of the forged left-most one.
    resolved = resolve_client_ip("10.0.0.9", "6.6.6.6, 198.51.100.7, 172.16.5.4", TRUSTED)
    assert resolved == "198.51.100.7"


def test_all_trusted_chain_returns_the_leftmost_entry() -> None:
    assert resolve_client_ip("10.0.0.9", "10.0.0.5, 172.16.0.1", TRUSTED) == "10.0.0.5"


def test_malformed_rightmost_hop_makes_the_chain_untrustworthy() -> None:
    assert resolve_client_ip("10.0.0.9", "198.51.100.7, not-an-ip", TRUSTED) == "10.0.0.9"


def test_malformed_leftmost_hop_is_never_reached() -> None:
    # The untrusted, well-formed hop is found first, so the garbage stays unused.
    assert resolve_client_ip("10.0.0.9", "not-an-ip, 198.51.100.7", TRUSTED) == "198.51.100.7"


def test_no_peer_address_returns_none() -> None:
    assert resolve_client_ip(None, "203.0.113.9", TRUSTED) is None


def test_ports_and_ipv6_forms_are_parsed() -> None:
    assert resolve_client_ip("10.0.0.9", "203.0.113.9:51234", TRUSTED) == "203.0.113.9"
    assert resolve_client_ip("10.0.0.9", "2001:db8::1", [ip_network("10.0.0.0/8")]) == "2001:db8::1"


# --------------------------------------------------------------------------- #
# End to end: the audit trail records the resolved address
# --------------------------------------------------------------------------- #
async def test_audit_records_the_peer_when_no_proxy_is_trusted(
    client, session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", [])  # nothing is trusted
    await create_user(session_factory)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": OWNER_EMAIL, "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert response.status_code == 401

    async with session_factory() as session:
        entry = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "login_failed").limit(1)
            )
        ).scalar_one()
    assert entry.ip_address == "127.0.0.1"  # the real peer, not the spoofed header


async def test_audit_records_the_forwarded_client_behind_a_trusted_proxy(
    client, session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.0/8"])
    await create_user(session_factory)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": OWNER_EMAIL, "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert response.status_code == 401

    async with session_factory() as session:
        entry = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "login_failed").limit(1)
            )
        ).scalar_one()
    assert entry.ip_address == "203.0.113.9"
