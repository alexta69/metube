# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub private vulnerability reporting](https://github.com/alexta69/metube/security/advisories/new)
(Security tab → "Report a vulnerability"). Do **not** open a public issue for
security problems.

You can expect an initial response within a few days. Please include a
reproduction and the MeTube release version (visible in the UI footer).

## Supported versions

MeTube is continuously released; only the **latest release** is supported.
Update to the current Docker image before reporting.

## Scope notes

MeTube ships **without authentication by design** — it is intended to run on a
trusted network or behind an authenticating reverse proxy (see the
[wiki](https://github.com/alexta69/metube/wiki/Reverse-proxy-configurations)).
Reports that reduce to "the UI is reachable without a login" are expected
behavior, not vulnerabilities.
