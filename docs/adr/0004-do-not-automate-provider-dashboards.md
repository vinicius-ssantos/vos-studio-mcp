# ADR-0004 — Do not automate provider dashboards

Status: Accepted  
Date: 2026-05-21

## Context

Provider dashboards such as Freepik, Magnific, and Higgsfield may include paid plan benefits, interactive interfaces, and usage policies. Automating those dashboards with browser automation could put accounts and client operations at risk.

## Decision

VOS Studio MCP will not use Playwright, Selenium, scraping, logged-in browser automation, or simulated human clicks to operate provider dashboards.

## Alternatives considered

- Browser automation: rejected due to compliance and account-risk concerns.
- Manual assisted execution: accepted for dashboard workflows.
- Official API/MCP/CLI execution: accepted for automation when cost and permissions are clear.

## Consequences

This reduces legal, account, and operational risk.

The tradeoff is that workflows using dashboard-only benefits remain human-executed.

## Impact on VOS Studio MCP

The MCP may create manual execution packs containing prompts, parameters, references, and checklists.

It must not open dashboards, log into provider accounts, click generate buttons, or download results through automated sessions.
