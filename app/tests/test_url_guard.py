"""Tests for the SSRF URL guard (``url_guard.validate_url``)."""

from __future__ import annotations

import socket
import unittest
from unittest import mock

import url_guard
from url_guard import (
    validate_url,
    _address_allowed_at_connect,
    _guarded_getaddrinfo,
    install_socket_guard,
)


def _addrinfo(*addrs, family=socket.AF_INET):
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (addr, 0)) for addr in addrs]


class NonUrlInputTests(unittest.TestCase):
    """Bare IDs and yt-dlp search/extractor prefixes must pass untouched."""

    def test_bare_video_id_allowed(self):
        self.assertIsNone(validate_url("dQw4w9WgXcQ"))

    def test_ytsearch_prefix_allowed(self):
        self.assertIsNone(validate_url("ytsearch:some song"))

    def test_empty_string_allowed(self):
        self.assertIsNone(validate_url(""))

    def test_non_string_rejected(self):
        self.assertIsNotNone(validate_url(None))


class SchemeTests(unittest.TestCase):
    def test_file_scheme_blocked(self):
        self.assertIsNotNone(validate_url("file:///etc/passwd"))

    def test_ftp_scheme_blocked(self):
        self.assertIsNotNone(validate_url("ftp://example.com/x"))

    def test_data_scheme_blocked(self):
        self.assertIsNotNone(validate_url("data://text/plain;base64,AAAA"))


class HostnameBlocklistTests(unittest.TestCase):
    def test_localhost_blocked_without_lookup(self):
        with mock.patch("url_guard.socket.getaddrinfo") as gai:
            self.assertIsNotNone(validate_url("http://localhost:8080/x"))
            gai.assert_not_called()

    def test_localhost_subdomain_blocked(self):
        self.assertIsNotNone(validate_url("http://foo.localhost/x"))

    def test_gcp_metadata_name_blocked(self):
        self.assertIsNotNone(validate_url("http://metadata.google.internal/x"))


class AddressResolutionTests(unittest.TestCase):
    def _validate_with_addrs(self, url, *addrs, family=socket.AF_INET):
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo(*addrs, family=family)):
            return validate_url(url)

    def test_public_https_allowed(self):
        self.assertIsNone(self._validate_with_addrs("https://youtube.com/watch?v=x", "142.250.1.1"))

    def test_public_http_allowed(self):
        self.assertIsNone(self._validate_with_addrs("http://example.com/x", "93.184.216.34"))

    def test_link_local_metadata_blocked(self):
        self.assertIsNotNone(self._validate_with_addrs("http://metadata/x", "169.254.169.254"))

    def test_loopback_ipv4_blocked(self):
        self.assertIsNotNone(self._validate_with_addrs("http://127.0.0.1/x", "127.0.0.1"))

    def test_private_rfc1918_blocked(self):
        self.assertIsNotNone(self._validate_with_addrs("http://intranet/x", "10.0.0.5"))

    def test_decimal_ip_form_blocked(self):
        # 2852039166 == 169.254.169.254; the OS resolver normalizes it.
        self.assertIsNotNone(self._validate_with_addrs("http://2852039166/x", "169.254.169.254"))

    def test_ipv6_loopback_blocked(self):
        self.assertIsNotNone(
            self._validate_with_addrs("http://[::1]/x", "::1", family=socket.AF_INET6)
        )

    def test_ipv4_mapped_ipv6_metadata_blocked(self):
        self.assertIsNotNone(
            self._validate_with_addrs(
                "http://evil/x", "::ffff:169.254.169.254", family=socket.AF_INET6
            )
        )

    def test_mixed_public_and_private_blocked(self):
        # If any resolved address is internal, reject the whole URL.
        self.assertIsNotNone(self._validate_with_addrs("http://mixed/x", "142.250.1.1", "127.0.0.1"))

    def test_resolution_failure_is_rejected(self):
        # Fail closed: an unresolvable host cannot be verified as non-internal.
        with mock.patch("url_guard.socket.getaddrinfo", side_effect=socket.gaierror):
            self.assertIsNotNone(validate_url("http://does-not-resolve.example/x"))


class ConnectAddressPolicyTests(unittest.TestCase):
    """Connect-time policy: allow global + loopback, block everything else."""

    def test_global_allowed(self):
        self.assertTrue(_address_allowed_at_connect("142.250.1.1"))

    def test_loopback_allowed(self):
        # Loopback stays reachable so locally-configured proxies keep working.
        self.assertTrue(_address_allowed_at_connect("127.0.0.1"))
        self.assertTrue(_address_allowed_at_connect("::1"))

    def test_link_local_metadata_blocked(self):
        self.assertFalse(_address_allowed_at_connect("169.254.169.254"))

    def test_private_blocked(self):
        self.assertFalse(_address_allowed_at_connect("10.0.0.5"))
        self.assertFalse(_address_allowed_at_connect("192.168.1.10"))

    def test_ipv4_mapped_metadata_blocked(self):
        self.assertFalse(_address_allowed_at_connect("::ffff:169.254.169.254"))


class GuardedGetaddrinfoTests(unittest.TestCase):
    def test_internal_only_raises(self):
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("169.254.169.254")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("metadata", 80)

    def test_filters_internal_keeps_global(self):
        # Split-horizon rebinding: keep the public address, drop the internal one.
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("142.250.1.1", "10.0.0.1")):
            results = _guarded_getaddrinfo("mixed", 80)
        self.assertEqual([r[4][0] for r in results], ["142.250.1.1"])

    def test_loopback_passes(self):
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            results = _guarded_getaddrinfo("localproxy", 9050)
        self.assertEqual([r[4][0] for r in results], ["127.0.0.1"])


class InstallSocketGuardTests(unittest.TestCase):
    def test_install_replaces_and_is_idempotent(self):
        original = socket.getaddrinfo
        try:
            install_socket_guard()
            self.assertIs(socket.getaddrinfo, url_guard._guarded_getaddrinfo)
            # Re-installing must not wrap the wrapper (real fn captured at import).
            install_socket_guard()
            self.assertIs(socket.getaddrinfo, url_guard._guarded_getaddrinfo)
        finally:
            socket.getaddrinfo = original


if __name__ == "__main__":
    unittest.main()
