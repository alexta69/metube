"""Lightweight SSRF guard for user-submitted URLs.

MeTube hands user-submitted URLs to yt-dlp, whose generic extractor will fetch
any ``http(s)`` URL. Without a guard, an attacker can make the server fetch
internal endpoints (cloud metadata services, loopback, RFC1918 hosts, etc.) and
have the response saved to the download directory and served back.

This module provides two layers:

* ``validate_url`` — a cheap validator applied at every URL ingress.
* ``install_socket_guard`` — a connect-time ``getaddrinfo`` guard installed in
  the download subprocess, which re-validates every resolved address and so
  covers redirects, DNS rebinding, and media URLs yt-dlp derives from remote
  metadata — for any backend that resolves through Python's socket module.

Known limitations — network isolation (e.g. Docker) remains the backstop for
all of these:

* The socket guard is installed only in the download subprocess. Metadata
  extraction (``ytdl.DownloadQueue.__extract_info``) runs in the main process,
  where installing a process-wide guard would reject the server's own bind on
  ``HOST=0.0.0.0``. So extraction — which also follows redirects — is covered
  only by ``validate_url`` at ingress, not at connect time; a redirect from an
  allowed host to an internal one during extraction is not blocked (a lower-
  impact, blind SSRF, since the extraction response is not written to disk).
* Native resolvers (curl_cffi/libcurl via ``--impersonate``) resolve outside
  Python's socket module and bypass the connect-time guard entirely.
"""

import ipaddress
import logging
import socket
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger('url_guard')

_ALLOWED_SCHEMES = ('http', 'https')

# Ports to assume when a configured proxy URL omits one, per proxy scheme.
_PROXY_DEFAULT_PORTS = {
    'http': 80,
    'https': 443,
    'socks4': 1080,
    'socks4a': 1080,
    'socks5': 1080,
    'socks5h': 1080,
}

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


def _normalise_ip(addr: str):
    """Parse *addr*, unwrapping IPv4-mapped IPv6 (e.g. ``::ffff:169.254.169.254``)
    so the embedded IPv4 address is judged on its own merits. Returns ``None``
    when *addr* is not a valid IP literal."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip


def _address_is_global(addr: str) -> bool:
    ip = _normalise_ip(addr)
    return ip is not None and ip.is_global


def _address_allowed_at_connect(addr: str, allow_loopback: bool = False) -> bool:
    """True if *addr* may be connected to at download time.

    Permits global addresses only. Loopback is permitted just for the specific
    host:port of an operator-configured proxy (see ``_loopback_endpoint_allowed``),
    never as a blanket rule: media URLs that yt-dlp derives from a remote manifest
    are attacker-controlled and reach this policy without passing ``validate_url``,
    so a general loopback allowance would let a hostile playlist read any service
    on the server's loopback interface. Blocks link-local (cloud metadata at
    169.254.169.254), private (RFC1918), unique-local and every other non-global
    range.
    """
    ip = _normalise_ip(addr)
    if ip is None:
        return False
    return ip.is_global or (allow_loopback and ip.is_loopback)


def _proxy_endpoint(proxy_url: str):
    """Parse a proxy URL into a ``(hostname, port)`` pair, or ``None`` if it has
    no usable host. Used to scope the loopback allowance to that endpoint alone."""
    if not isinstance(proxy_url, str) or not proxy_url.strip():
        return None
    candidate = proxy_url.strip()
    if '://' not in candidate:
        # Bare host:port, as accepted by the *_proxy environment variables.
        candidate = '//' + candidate
    try:
        parts = urlsplit(candidate)
        hostname, port = parts.hostname, parts.port
    except ValueError:
        return None
    if not hostname:
        return None
    if port is None:
        port = _PROXY_DEFAULT_PORTS.get(parts.scheme.lower())
    return (hostname.rstrip('.').lower(), port)


def _collect_proxy_endpoints(proxy_urls) -> set:
    """Endpoints of every proxy this download may legitimately dial: the explicit
    yt-dlp ``proxy`` option plus the ``*_proxy`` environment variables yt-dlp falls
    back to. All are operator-configured, unlike the URLs inside fetched media."""
    candidates = list(proxy_urls) + list(urllib.request.getproxies().values())
    return {ep for ep in map(_proxy_endpoint, candidates) if ep is not None}


# Captured at import so re-installing the guard never wraps the wrapper.
_real_getaddrinfo = socket.getaddrinfo

# Populated by install_socket_guard; empty means no loopback destination is allowed.
_allowed_loopback_endpoints: set = set()


def _normalise_port(port):
    if isinstance(port, str):
        try:
            return int(port)
        except ValueError:
            try:
                return socket.getservbyname(port)
            except OSError:
                return None
    return port


def _loopback_endpoint_allowed(host, port) -> bool:
    if not _allowed_loopback_endpoints or host is None:
        return False
    return (str(host).rstrip('.').lower(), _normalise_port(port)) in _allowed_loopback_endpoints


def _guarded_getaddrinfo(host, *args, **kwargs):
    results = _real_getaddrinfo(host, *args, **kwargs)
    # Mirrors getaddrinfo(host, port, ...): port is the first optional argument.
    port = args[0] if args else kwargs.get('port')
    allow_loopback = _loopback_endpoint_allowed(host, port)
    allowed = [r for r in results if _address_allowed_at_connect(r[4][0], allow_loopback)]
    if not allowed:
        raise socket.gaierror(f'Refusing to connect to non-global address for host {host!r}')
    return allowed


def install_socket_guard(allow_private: bool = False, proxy_urls=()) -> None:
    """Enforce the no-internal-hosts policy at actual connection time.

    ``validate_url`` only checks the *submitted* URL string; yt-dlp then follows
    HTTP redirects and resolves media URLs from remote metadata without
    re-validating them. Installing this in the download subprocess re-checks
    every resolved address at connect time, covering redirects, DNS rebinding and
    manifest-derived media URLs for any networking backend that resolves through
    Python's socket module (urllib, requests). Native resolvers — notably
    curl_cffi/libcurl used by ``--impersonate`` — bypass this and rely on network
    isolation as the backstop.

    *proxy_urls* are the operator's configured proxies (yt-dlp's ``proxy`` option;
    the ``*_proxy`` environment variables are picked up automatically). A proxy on
    loopback is reachable at its own host:port, and nothing else on loopback is.
    That costs proxied setups nothing: yt-dlp resolves the proxy itself at exactly
    that host:port, and a media URL is either handed to the proxy unresolved or
    resolved on its own merits — never inheriting the proxy's allowance.

    When *allow_private* is set (``ALLOW_PRIVATE_ADDRESSES``), the guard is not
    installed at all, so proxy/VPN setups that route through private or Fake-IP
    ranges keep working.
    """
    if allow_private:
        return
    _allowed_loopback_endpoints.clear()
    _allowed_loopback_endpoints.update(_collect_proxy_endpoints(proxy_urls))
    for host, port in sorted(_allowed_loopback_endpoints, key=lambda ep: (ep[0], ep[1] or 0)):
        ip = _normalise_ip(host)
        if ip is not None and ip.is_loopback:
            log.info(f'Allowing connections to configured loopback proxy {host}:{port}')
    socket.getaddrinfo = _guarded_getaddrinfo


def validate_url(url: str, allow_private: bool = False) -> str | None:
    """Return an error message if the URL is disallowed, else ``None``.

    Inputs without a ``://`` scheme separator (bare video IDs, ``ytsearch:``
    and other yt-dlp search/extractor prefixes) are allowed unchanged so that
    non-URL entries keep working.

    When *allow_private* is set (``ALLOW_PRIVATE_ADDRESSES``), the internal-host
    and internal-address checks are skipped so that trusted proxy/VPN setups —
    e.g. Fake-IP clients that resolve YouTube to ``198.18.0.0/15`` — can be used.
    Scheme validation (http/https only) still applies.
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

    if allow_private:
        # Environment is explicitly trusted: skip the SSRF address checks.
        return None

    if _hostname_is_blocked(hostname):
        return f'Refusing to fetch internal host "{hostname}"'

    try:
        addrinfo = socket.getaddrinfo(hostname, parts.port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Fail closed: a host we cannot resolve is a host we cannot verify as
        # non-internal, so refuse it rather than letting the download proceed
        # to a target that may resolve differently at fetch time.
        return f'Could not resolve host "{hostname}"'
    except (UnicodeError, ValueError):
        return f'Invalid host "{hostname}"'

    for family, _type, _proto, _canonname, sockaddr in addrinfo:
        addr = sockaddr[0]
        if not _address_is_global(addr):
            return f'Refusing to fetch internal address "{addr}" for host "{hostname}"'

    return None
