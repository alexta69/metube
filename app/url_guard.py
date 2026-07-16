"""Lightweight SSRF guard for user-submitted URLs.

MeTube hands user-submitted URLs to yt-dlp, whose generic extractor will fetch
any ``http(s)`` URL. Without a guard, an attacker can make the server fetch
internal endpoints (cloud metadata services, loopback, RFC1918 hosts, etc.) and
have the response saved to the download directory and served back.

This module provides a single cheap validator applied at every URL ingress. It
intentionally does NOT attempt DNS-rebinding pinning, redirect-chain
re-validation, or validation of every media URL yt-dlp derives from remote
metadata — network isolation (e.g. Docker) remains the backstop for those.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlsplit

log = logging.getLogger('url_guard')

_ALLOWED_SCHEMES = ('http', 'https')

# Hostnames that must be blocked without needing a lookup. ``localhost`` and any
# subdomain of it are conventionally loopback, and the GCP metadata name is a
# well-known SSRF target that may resolve via a resolver we don't control.
_BLOCKED_HOSTNAMES = ('localhost', 'metadata.google.internal')


def _hostname_is_blocked(hostname: str) -> bool:
    host = hostname.rstrip('.').lower()
    for blocked in _BLOCKED_HOSTNAMES:
        if host == blocked or host.endswith('.' + blocked):
            return True
    return False


def _address_is_global(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    # Unwrap IPv4-mapped/compatible IPv6 (e.g. ::ffff:169.254.169.254) so the
    # embedded IPv4 address is judged on its own merits.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


def validate_url(url: str) -> str | None:
    """Return an error message if the URL is disallowed, else ``None``.

    Inputs without a ``://`` scheme separator (bare video IDs, ``ytsearch:``
    and other yt-dlp search/extractor prefixes) are allowed unchanged so that
    non-URL entries keep working.
    """
    if not isinstance(url, str):
        return 'Invalid URL'

    candidate = url.strip()
    if '://' not in candidate:
        # Not an absolute URL: bare video IDs, ytsearch: prefixes, etc.
        return None

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return f'URL scheme "{parts.scheme}" is not allowed (only http and https)'

    hostname = parts.hostname
    if not hostname:
        return 'URL is missing a host'

    if _hostname_is_blocked(hostname):
        return f'Refusing to fetch internal host "{hostname}"'

    try:
        addrinfo = socket.getaddrinfo(hostname, parts.port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Let yt-dlp surface a normal resolution error rather than masking it.
        return None
    except (UnicodeError, ValueError):
        return f'Invalid host "{hostname}"'

    for family, _type, _proto, _canonname, sockaddr in addrinfo:
        addr = sockaddr[0]
        if not _address_is_global(addr):
            return f'Refusing to fetch internal address "{addr}" for host "{hostname}"'

    return None
