# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Yes    |

Older releases are not actively maintained. Please update to the latest version before reporting an issue.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability, please report it privately via GitHub:

1. Go to the [Security tab](https://github.com/wulfftech/hacs-irrigation-caddy/security) of this repository
2. Click **"Report a vulnerability"**
3. Fill in the details and submit

You can also email **hello@wulfftech.com.au** with the subject line `[SECURITY] hacs-irrigation-caddy`.

## What to Include

Please include as much of the following as possible:

- Type of issue (e.g. unauthenticated API access, credential exposure, etc.)
- The file(s) and line number(s) involved
- Step-by-step instructions to reproduce
- Proof-of-concept or exploit code (if possible)
- Impact assessment — how could an attacker exploit this?

## Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgement | Within 48 hours |
| Initial assessment | Within 5 business days |
| Fix / mitigation | Dependent on severity |

## Scope

This integration communicates exclusively on your **local network** with your Irrigation Caddy device. It does not transmit data to any external server. The main attack surface is:

- Unauthenticated HTTP to the controller (the device itself has no authentication by default)
- Home Assistant configuration exposure

## Out of Scope

- Vulnerabilities in the Irrigation Caddy firmware itself (contact KGControls)
- Vulnerabilities in Home Assistant core (report to the [HA security team](https://www.home-assistant.io/security/))
