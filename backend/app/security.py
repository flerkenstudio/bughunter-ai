"""Safety gates: target policy, identity handshake, patch path validation.

External URLs are allowed by default, but private, loopback and link-local
addresses stay blocked so the API cannot be turned into an internal port
scanner. The bundled demo store is the only target that presents an identity
marker, and patch verification is restricted to it.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .catalog import SCOPES
from .config import Settings

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
DEMO_TARGET_MARKER = "nimbus-supply"

# Metadata endpoints used by cloud providers; never reachable, always refused.
BLOCKED_IPS = {"169.254.169.254", "169.254.170.2", "100.100.100.200", "fd00:ec2::254"}

PATCH_ALLOWED_PREFIXES = ("demo-store/", "backend/", "tests/", "frontend/", "docs/")
PATCH_FORBIDDEN_PARTS = (".git", ".env", "secrets", "id_rsa", ".pem")


class UnsafeTargetError(ValueError):
    """The request points somewhere the target policy forbids."""


class TargetUnavailableError(RuntimeError):
    """The target could not be reached; this is infrastructure, not an app bug."""


class TargetIdentityError(ValueError):
    """The target responded but is not the approved demo application."""


@dataclass(frozen=True)
class Target:
    base_url: str
    host: str
    port: int
    is_demo: bool
    is_loopback: bool

    @property
    def kind(self) -> str:
        return "demo" if self.is_demo else "external"


def validate_scope(scope: list[str]) -> list[str]:
    unknown = [area for area in scope if area not in SCOPES]
    if unknown:
        raise UnsafeTargetError(
            f"unknown scope {unknown}; allowed scopes are {list(SCOPES)}"
        )
    return scope


def _address_is_blocked(address: ipaddress._BaseAddress, settings: Settings) -> str | None:
    if str(address) in BLOCKED_IPS:
        return "cloud metadata endpoint"
    if address.is_loopback:
        return None  # loopback is allowed for the bundled demo store
    if address.is_private and not settings.allow_private_targets:
        return "private address"
    if address.is_link_local and not settings.allow_private_targets:
        return "link-local address"
    if address.is_reserved or address.is_multicast or address.is_unspecified:
        return "reserved address"
    return None


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    return sorted({info[4][0] for info in infos})


def _assert_host_is_allowed(host: str, settings: Settings) -> None:
    if settings.allowed_hosts and host not in settings.allowed_hosts and host not in LOOPBACK_HOSTS:
        raise UnsafeTargetError(
            f"host '{host}' is not in BUGHUNTER_ALLOWED_HOSTS ({list(settings.allowed_hosts)})"
        )

    if host in LOOPBACK_HOSTS:
        return

    if not settings.allow_external_targets:
        raise UnsafeTargetError(
            "external targets are disabled; set BUGHUNTER_ALLOW_EXTERNAL_TARGETS=1 to enable"
        )

    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None

    if literal is not None:
        reason = _address_is_blocked(literal, settings)
        if reason:
            raise UnsafeTargetError(f"refusing to test {host}: {reason}")
        return

    # Hostnames are resolved so a public name cannot point at internal space.
    # A DNS failure is left to the preflight, which reports it as infrastructure.
    for resolved in _resolve(host):
        try:
            address = ipaddress.ip_address(resolved)
        except ValueError:
            continue
        reason = _address_is_blocked(address, settings)
        if reason:
            raise UnsafeTargetError(f"refusing to test {host}: resolves to {resolved} ({reason})")


def validate_target(base_url: str, settings: Settings) -> Target:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetError("only http and https targets are allowed")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("targets with embedded credentials are not allowed")
    if not parsed.hostname:
        raise UnsafeTargetError("target URL must include a host")

    host = parsed.hostname.lower()
    is_loopback = host in LOOPBACK_HOSTS
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if is_loopback and settings.allowed_ports and port not in settings.allowed_ports:
        raise UnsafeTargetError(
            f"port {port} is not allowlisted; allowed ports: {list(settings.allowed_ports)}"
        )

    _assert_host_is_allowed(host, settings)

    return Target(
        base_url=base_url.rstrip("/"),
        host=host,
        port=port,
        is_demo=is_loopback,
        is_loopback=is_loopback,
    )


def fetch_target_health(target: Target, timeout: float = 10.0) -> tuple[int, str | None]:
    """Reach the target. Returns (status, demo marker).

    httpx is used instead of urllib because it carries certifi, so HTTPS targets
    verify correctly even when the interpreter has no system CA bundle.
    """
    url = f"{target.base_url}/health" if target.is_demo else target.base_url
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "BugHunterAI/0.1"},
        )
        return response.status_code, response.headers.get("X-Demo-Target")
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        raise TargetUnavailableError(f"target unreachable at {url}: {exc}") from exc


def probe_target(target: Target, settings: Settings, timeout: float = 10.0) -> None:
    """Confirm the target is reachable, and that the demo target is really ours."""
    status, marker = fetch_target_health(target, timeout=timeout)

    if target.is_demo:
        if settings.require_demo_target and marker != DEMO_TARGET_MARKER:
            raise TargetIdentityError(
                "target did not present the approved demo-store identity marker"
            )
        if status >= 500:
            raise TargetUnavailableError(f"demo store returned HTTP {status}")
        return

    if status >= 500:
        raise TargetUnavailableError(f"target returned HTTP {status} on the first request")


def validate_patch(diff: str) -> list[str]:
    """Reject patches that escape the workspace or touch secrets."""
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++ ", "--- ")):
            raw = line[4:].strip().split("\t")[0]
            if raw == "/dev/null":
                continue
            if raw.startswith(("a/", "b/")):
                raw = raw[2:]
            paths.append(raw)

    if not paths:
        raise UnsafeTargetError("patch does not contain file headers")

    for path in paths:
        if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
            raise UnsafeTargetError(f"absolute paths are not allowed in patches: {path}")
        if ".." in path.split("/") or "\\" in path:
            raise UnsafeTargetError(f"path traversal is not allowed in patches: {path}")
        lowered = path.lower()
        if any(part in lowered for part in PATCH_FORBIDDEN_PARTS):
            raise UnsafeTargetError(f"patch touches a protected path: {path}")
        if not path.startswith(PATCH_ALLOWED_PREFIXES):
            raise UnsafeTargetError(f"patch path is outside the allowed roots: {path}")

    return sorted(set(paths))