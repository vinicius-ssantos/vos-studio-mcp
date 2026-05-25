# ADR-0032 — SSRF Protection for Outbound Webhook Delivery

**Status:** Accepted  
**Date:** 2026-05-24  
**Issue:** #47

---

## Context

Issue #33 introduced outbound webhooks: the server POSTs job-completion
notifications to a client-configured `webhook_url` stored in the database.
Because the server makes an outbound network request to a URL that a client
(or an operator acting on their behalf) can configure, the feature is
inherently susceptible to Server-Side Request Forgery (SSRF).

MCP security guidance explicitly calls out SSRF as a risk in any system that
can be directed to make outbound HTTP requests. OWASP classifies this as a
critical vulnerability when the target URL originates from user input.

Specific threat vectors:
- Client registers `https://169.254.169.254/latest/meta-data/` → exfiltrates
  AWS/GCP cloud metadata.
- Client registers `http://10.0.0.1/admin` → probes internal network services.
- Client registers `https://attacker.example.com` which returns a redirect to
  `http://localhost:6379` → Redis command injection.

---

## Decision

All outbound webhook URLs **must** pass an SSRF guard before:
1. Being persisted to the database (via `set_client_webhook`).
2. Being used to deliver a notification (inside `_deliver`).

The guard enforces:

| Rule | Detail |
|---|---|
| HTTPS only | `http://` and any other scheme are rejected |
| No loopback | 127.x.x.x, ::1, localhost |
| No RFC 1918 private | 10.x, 172.16-31.x, 192.168.x |
| No link-local | 169.254.x.x (includes cloud metadata), fe80:: |
| No multicast | 224.x+, ff:: |
| No unspecified | 0.0.0.0, :: |
| No reserved | Any `ipaddress.is_reserved` address |
| DNS-resolves to public IP | Every resolved address is checked |

Redirects are not followed for POST requests (httpx default). This prevents
an open redirect from bypassing the guard.

The guard is implemented in `services/webhook_ssrf_guard.py` as:
- `validate_webhook_url(url)` — synchronous; suitable for registration checks
  and Celery task contexts.
- `check_webhook_url(url)` — async thin wrapper using `run_in_executor` to
  avoid blocking the event loop during DNS resolution.

---

## Consequences

**Positive:**
- SSRF attacks through configured webhook URLs are blocked at two independent
  checkpoints (registration + delivery).
- Operators and clients receive a clear, actionable error message when an
  invalid URL is provided.
- Future providers and features that make outbound requests can reuse the
  same guard.

**Negative:**
- Clients with webhooks hosted on internal networks (edge case: private
  cloud deployments) cannot use the outbound notification feature. They would
  need to expose an HTTPS endpoint on the public internet, or an allowlist
  mechanism would need to be added in the future.

**Neutral:**
- DNS resolution adds ~1–100 ms to the registration path; this is acceptable.
- The guard runs synchronously in the Celery delivery task (already in a
  thread context); this does not block an event loop.
