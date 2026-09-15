"""Tests for the SSRF URL guard (``url_guard.validate_url``)."""

from __future__ import annotations

import socket
import unittest
from unittest import mock

import url_guard
from url_guard import (
    validate_url,
    _address_allowed_at_connect,
    _address_is_global,
    _guarded_getaddrinfo,
    _url_endpoint,
    download_proxies,
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
    """Connect-time policy: allow global, plus anything at a destination the
    caller has established is the operator's configured proxy."""

    def test_global_allowed(self):
        self.assertTrue(_address_allowed_at_connect("142.250.1.1"))

    def test_loopback_blocked_by_default(self):
        # A blanket loopback allowance is what let manifest-derived media URLs
        # reach services on the server's own loopback interface.
        self.assertFalse(_address_allowed_at_connect("127.0.0.1"))
        self.assertFalse(_address_allowed_at_connect("::1"))

    def test_loopback_allowed_only_when_opted_in(self):
        self.assertTrue(_address_allowed_at_connect("127.0.0.1", is_allowed_endpoint=True))
        self.assertTrue(_address_allowed_at_connect("::1", is_allowed_endpoint=True))

    def test_proxy_opt_in_covers_any_internal_range(self):
        # A proxy is just as legitimately on the LAN or a VPN range as on
        # loopback (#1055): the allowance follows the operator's configured
        # endpoint, not a particular address family.
        self.assertTrue(_address_allowed_at_connect("10.1.20.30", is_allowed_endpoint=True))
        self.assertTrue(_address_allowed_at_connect("192.168.1.10", is_allowed_endpoint=True))
        self.assertTrue(_address_allowed_at_connect("fd00::1", is_allowed_endpoint=True))

    def test_opt_in_still_rejects_non_addresses(self):
        self.assertFalse(_address_allowed_at_connect("not-an-ip", is_allowed_endpoint=True))

    def test_link_local_metadata_blocked(self):
        self.assertFalse(_address_allowed_at_connect("169.254.169.254"))

    def test_private_blocked(self):
        self.assertFalse(_address_allowed_at_connect("10.0.0.5"))
        self.assertFalse(_address_allowed_at_connect("192.168.1.10"))

    def test_ipv4_mapped_metadata_blocked(self):
        self.assertFalse(_address_allowed_at_connect("::ffff:169.254.169.254"))


class TunnelledIPv4Tests(unittest.TestCase):
    """IPv6 transition forms that carry an IPv4 address the outer address hides.

    ``is_global`` looks only at the outer address, so a form that tunnels an
    internal IPv4 has to be unwrapped before it is judged (GHSA-5mq5-qr7m-f4wx).
    """

    def test_nat64_well_known_prefix_blocked(self):
        # 2000::/3 global unicast on its face; carries the metadata address.
        self.assertFalse(_address_is_global("64:ff9b::a9fe:a9fe"))
        self.assertFalse(_address_is_global("64:ff9b::7f00:1"))
        self.assertFalse(_address_allowed_at_connect("64:ff9b::a9fe:a9fe"))

    def test_nat64_carrying_a_public_address_allowed(self):
        self.assertTrue(_address_is_global("64:ff9b::8.8.8.8"))

    def test_ipv4_compatible_form_blocked(self):
        # The deprecated ::/96 form, likewise global-looking to is_global.
        self.assertFalse(_address_is_global("::a9fe:a9fe"))
        self.assertFalse(_address_allowed_at_connect("::a9fe:a9fe"))

    def test_sixtofour_and_teredo_stay_blocked(self):
        # Python rejects these ranges wholesale. Unwrapping must not promote a
        # blocked address to an allowed one just because the payload is global.
        self.assertFalse(_address_is_global("2002:a9fe:a9fe::"))
        self.assertFalse(_address_is_global("2002:0808:0808::"))
        self.assertFalse(_address_is_global("2001:0:4136:e378:8000:63bf:3fff:fdd2"))

    def test_plain_addresses_unaffected(self):
        self.assertTrue(_address_is_global("142.250.1.1"))
        self.assertTrue(_address_is_global("2607:f8b0:4004:c07::64"))
        self.assertFalse(_address_is_global("not-an-ip"))

    def test_tunnelled_form_blocked_at_ingress(self):
        with mock.patch(
            "url_guard.socket.getaddrinfo",
            return_value=_addrinfo("64:ff9b::a9fe:a9fe", family=socket.AF_INET6),
        ):
            self.assertIsNotNone(validate_url("http://nat64.example/x"))


class EndpointParsingTests(unittest.TestCase):
    def test_explicit_port(self):
        self.assertEqual(_url_endpoint("http://127.0.0.1:9050"), ("127.0.0.1", 9050))

    def test_default_port_per_scheme(self):
        self.assertEqual(_url_endpoint("socks5://127.0.0.1"), ("127.0.0.1", 1080))
        self.assertEqual(_url_endpoint("http://127.0.0.1"), ("127.0.0.1", 80))

    def test_bare_host_port(self):
        self.assertEqual(_url_endpoint("127.0.0.1:8080"), ("127.0.0.1", 8080))

    def test_hostname_lowercased(self):
        self.assertEqual(_url_endpoint("http://LocalHost.:9050"), ("localhost", 9050))

    def test_ipv6_literal(self):
        self.assertEqual(_url_endpoint("http://[::1]:9050"), ("::1", 9050))

    def test_empty_and_invalid(self):
        self.assertIsNone(_url_endpoint(""))
        self.assertIsNone(_url_endpoint("   "))
        self.assertIsNone(_url_endpoint(None))
        self.assertIsNone(_url_endpoint("http://"))


class GuardedGetaddrinfoTests(unittest.TestCase):
    def setUp(self):
        # Default state: no proxy configured, so no loopback destination allowed.
        saved = set(url_guard._allowed_endpoints)
        url_guard._allowed_endpoints = set()
        self.addCleanup(lambda: setattr(url_guard, "_allowed_endpoints", saved))

    def test_internal_only_raises(self):
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("169.254.169.254")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("metadata", 80)

    def test_filters_internal_keeps_global(self):
        # Split-horizon rebinding: keep the public address, drop the internal one.
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("142.250.1.1", "10.0.0.1")):
            results = _guarded_getaddrinfo("mixed", 80)
        self.assertEqual([r[4][0] for r in results], ["142.250.1.1"])

    def test_loopback_blocked_without_matching_proxy(self):
        # The advisory case: an m3u8 segment URL pointing at a loopback service.
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("127.0.0.1", 9999)

    def test_loopback_allowed_at_configured_url_endpoint(self):
        url_guard._allowed_endpoints = {("127.0.0.1", 9050)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            results = _guarded_getaddrinfo("127.0.0.1", 9050)
        self.assertEqual([r[4][0] for r in results], ["127.0.0.1"])

    def test_loopback_blocked_at_other_port_on_proxy_host(self):
        # Same host as the proxy, different port: still off limits.
        url_guard._allowed_endpoints = {("127.0.0.1", 9050)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("127.0.0.1", 9999)

    def test_proxy_reachable_by_hostname(self):
        url_guard._allowed_endpoints = {("localhost", 9050)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            results = _guarded_getaddrinfo("localhost", 9050)
        self.assertEqual([r[4][0] for r in results], ["127.0.0.1"])

    def test_string_port_is_normalised(self):
        url_guard._allowed_endpoints = {("127.0.0.1", 9050)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            results = _guarded_getaddrinfo("127.0.0.1", "9050")
        self.assertEqual([r[4][0] for r in results], ["127.0.0.1"])

    def test_lan_proxy_reachable(self):
        # #1055: a socks5 proxy on the LAN, refused while the allowance was
        # loopback-only, which pushed operators to ALLOW_PRIVATE_ADDRESSES.
        url_guard._allowed_endpoints = {("10.1.20.30", 1080)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("10.1.20.30")):
            results = _guarded_getaddrinfo("10.1.20.30", 1080)
        self.assertEqual([r[4][0] for r in results], ["10.1.20.30"])

    def test_other_lan_host_still_blocked(self):
        # The allowance is the proxy's endpoint, not its subnet.
        url_guard._allowed_endpoints = {("10.1.20.30", 1080)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("10.1.20.31")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("10.1.20.31", 1080)

    def test_pot_provider_reachable_on_loopback(self):
        # #1064: the bundled PO token provider listens on loopback, and blocking
        # it left every default install downloading YouTube without a token.
        url_guard._allowed_endpoints = {("127.0.0.1", 4416)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            results = _guarded_getaddrinfo("127.0.0.1", 4416)
        self.assertEqual([r[4][0] for r in results], ["127.0.0.1"])

    def test_other_loopback_service_still_blocked(self):
        # MeTube's own port is one hop away on the same interface: allowing the
        # token provider must not allow the rest of loopback.
        url_guard._allowed_endpoints = {("127.0.0.1", 4416)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("127.0.0.1", 8081)

    def test_proxy_address_not_borrowable_by_another_host(self):
        # Matching is on the configured host string: a manifest URL that resolves
        # to the proxy's address under its own name gets no allowance.
        url_guard._allowed_endpoints = {("10.1.20.30", 1080)}
        with mock.patch("url_guard._real_getaddrinfo", return_value=_addrinfo("10.1.20.30")):
            with self.assertRaises(socket.gaierror):
                _guarded_getaddrinfo("evil.example", 1080)


class DownloadProxiesTests(unittest.TestCase):
    """The proxy map is assembled the way YoutubeDL.proxies assembles it."""

    def test_explicit_proxy_option_replaces_environment(self):
        with mock.patch("url_guard.urllib.request.getproxies",
                        return_value={"http": "http://env:3128", "no": "example.com"}):
            self.assertEqual(download_proxies({"proxy": "socks5h://tor:9050"}),
                             {"all": "socks5h://tor:9050"})

    def test_empty_proxy_option_means_no_proxy(self):
        self.assertEqual(download_proxies({"proxy": ""}), {"all": "__noproxy__"})

    def test_environment_used_when_no_proxy_option(self):
        with mock.patch("url_guard.urllib.request.getproxies",
                        return_value={"http": "http://env:3128"}):
            # http_proxy alone also covers https, as in yt-dlp.
            self.assertEqual(download_proxies({}),
                             {"http": "http://env:3128", "https": "http://env:3128"})

    def test_no_options_at_all(self):
        with mock.patch("url_guard.urllib.request.getproxies", return_value={}):
            self.assertEqual(download_proxies(), {})


class ProxiedHostnameTests(unittest.TestCase):
    """A proxy that resolves hostnames itself makes a local lookup both wrong
    and harmful, so the address check is skipped for hostnames behind one."""

    def _validate(self, url, proxies):
        with mock.patch("url_guard.socket.getaddrinfo") as gai:
            gai.side_effect = AssertionError("resolved a hostname that the proxy resolves")
            return validate_url(url, proxies=proxies)

    def test_socks5h_hostname_not_resolved(self):
        self.assertIsNone(self._validate("https://youtube.com/x", {"all": "socks5h://tor:9050"}))

    def test_plain_socks5_treated_as_remote_dns(self):
        # yt-dlp rewrites socks5 to socks5h on every request for compatibility.
        self.assertIsNone(self._validate("https://youtube.com/x", {"all": "socks5://tor:9050"}))

    def test_socks4a_hostname_not_resolved(self):
        self.assertIsNone(self._validate("https://youtube.com/x", {"all": "socks4a://tor:9050"}))

    def test_http_proxy_hostname_not_resolved(self):
        self.assertIsNone(self._validate("https://youtube.com/x", {"https": "http://squid:3128"}))

    def test_scheme_less_proxy_treated_as_http(self):
        self.assertIsNone(self._validate("https://youtube.com/x", {"all": "squid:3128"}))

    def test_per_scheme_entry_selected(self):
        # Only http is proxied here, so an https URL keeps the check.
        proxies = {"http": "http://squid:3128"}
        self.assertIsNone(self._validate("http://youtube.com/x", proxies))
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
            self.assertIsNotNone(validate_url("https://youtube.com/x", proxies=proxies))

    def test_socks4_still_resolved_locally(self):
        # SOCKS4 resolves in this process, so the address check still applies.
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
            self.assertIsNotNone(validate_url("https://youtube.com/x",
                                              proxies={"all": "socks4://tor:9050"}))

    def test_noproxy_host_still_resolved(self):
        # A host excluded from the proxy is fetched directly, so it is checked.
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo("169.254.169.254")):
            self.assertIsNotNone(validate_url(
                "http://metadata.internal/x",
                proxies={"all": "socks5h://tor:9050", "no": "metadata.internal"}))

    def test_noproxy_marker_keeps_check(self):
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
            self.assertIsNotNone(validate_url("https://youtube.com/x",
                                              proxies={"all": "__noproxy__"}))

    def test_ip_literal_still_checked_behind_a_proxy(self):
        # An IP literal needs no name resolution, so nothing leaks by judging it
        # and the proxy changes nothing: the request names this address either
        # way. Unmocked on purpose — getaddrinfo on a literal never hits DNS.
        self.assertIsNotNone(validate_url("http://169.254.169.254/latest/meta-data/",
                                          proxies={"all": "socks5h://tor:9050"}))

    def test_ipv6_literal_still_checked_behind_a_proxy(self):
        self.assertIsNotNone(validate_url("http://[::1]:8080/x",
                                          proxies={"all": "socks5h://tor:9050"}))

    def test_blocked_hostname_still_blocked_behind_a_proxy(self):
        self.assertIsNotNone(validate_url("http://localhost:8080/x",
                                          proxies={"all": "socks5h://tor:9050"}))

    def test_scheme_still_enforced_behind_a_proxy(self):
        self.assertIsNotNone(validate_url("file:///etc/passwd",
                                          proxies={"all": "socks5h://tor:9050"}))

    def test_unparseable_proxy_keeps_check(self):
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
            self.assertIsNotNone(validate_url("https://youtube.com/x",
                                              proxies={"all": "gopher://weird:70"}))

    def test_no_proxies_argument_keeps_check(self):
        # The default: callers that pass nothing get today's behaviour.
        with mock.patch("url_guard.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
            self.assertIsNotNone(validate_url("https://youtube.com/x"))


class AllowPrivateBypassTests(unittest.TestCase):
    """ALLOW_PRIVATE_ADDRESSES: trusted proxy/VPN environments opt out of the
    SSRF address checks (e.g. Fake-IP clients that resolve to 198.18.0.0/15)."""

    def test_internal_address_allowed_when_bypassed(self):
        # Fake-IP benchmarking range that is_global rejects by default.
        self.assertIsNone(validate_url("http://www.youtube.com/x", allow_private=True))

    def test_private_host_allowed_when_bypassed(self):
        # No DNS lookup needed: the bypass returns before resolution.
        with mock.patch("url_guard.socket.getaddrinfo") as gai:
            self.assertIsNone(validate_url("http://192.168.1.1/x", allow_private=True))
            gai.assert_not_called()

    def test_scheme_still_enforced_when_bypassed(self):
        self.assertIsNotNone(validate_url("file:///etc/passwd", allow_private=True))

    def test_socket_guard_not_installed_when_bypassed(self):
        original = socket.getaddrinfo
        try:
            install_socket_guard(allow_private=True)
            self.assertIs(socket.getaddrinfo, original)
        finally:
            socket.getaddrinfo = original


class InstallSocketGuardTests(unittest.TestCase):
    def setUp(self):
        original, saved = socket.getaddrinfo, set(url_guard._allowed_endpoints)
        self.addCleanup(lambda: setattr(socket, "getaddrinfo", original))
        self.addCleanup(lambda: setattr(url_guard, "_allowed_endpoints", saved))
        # Keep the host's own environment out of the assertions below.
        patcher = mock.patch("url_guard.urllib.request.getproxies", return_value={})
        self.getproxies = patcher.start()
        self.addCleanup(patcher.stop)

    def test_install_replaces_and_is_idempotent(self):
        install_socket_guard()
        self.assertIs(socket.getaddrinfo, url_guard._guarded_getaddrinfo)
        # Re-installing must not wrap the wrapper (real fn captured at import).
        install_socket_guard()
        self.assertIs(socket.getaddrinfo, url_guard._guarded_getaddrinfo)

    def test_no_proxy_means_no_loopback_allowance(self):
        install_socket_guard()
        self.assertEqual(url_guard._allowed_endpoints, set())

    def test_explicit_proxy_is_registered(self):
        install_socket_guard(proxy_urls=("socks5://127.0.0.1:9050",))
        self.assertEqual(url_guard._allowed_endpoints, {("127.0.0.1", 9050)})

    def test_unset_proxy_option_is_ignored(self):
        # ytdl_opts.get('proxy') is None when the operator configured no proxy.
        install_socket_guard(proxy_urls=(None,))
        self.assertEqual(url_guard._allowed_endpoints, set())

    def test_environment_proxies_are_registered(self):
        self.getproxies.return_value = {"http": "http://127.0.0.1:8080"}
        install_socket_guard()
        self.assertEqual(url_guard._allowed_endpoints, {("127.0.0.1", 8080)})

    def test_service_url_is_registered(self):
        install_socket_guard(service_urls=("http://127.0.0.1:4416",))
        self.assertEqual(url_guard._allowed_endpoints, {("127.0.0.1", 4416)})

    def test_service_and_proxy_endpoints_coexist(self):
        install_socket_guard(
            proxy_urls=("socks5://10.1.20.30:1080",),
            service_urls=("http://127.0.0.1:4416",),
        )
        self.assertEqual(
            url_guard._allowed_endpoints,
            {("10.1.20.30", 1080), ("127.0.0.1", 4416)},
        )

    def test_service_urls_reset_between_installs(self):
        install_socket_guard(service_urls=("http://127.0.0.1:4416",))
        install_socket_guard()
        self.assertEqual(url_guard._allowed_endpoints, set())

    def test_endpoints_reset_between_installs(self):
        install_socket_guard(proxy_urls=("http://127.0.0.1:8080",))
        install_socket_guard(proxy_urls=(None,))
        self.assertEqual(url_guard._allowed_endpoints, set())


if __name__ == "__main__":
    unittest.main()
