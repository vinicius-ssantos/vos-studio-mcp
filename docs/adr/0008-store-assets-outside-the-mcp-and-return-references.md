# ADR-0008 — Store assets outside the MCP and return references

Status: Accepted  
Date: 2026-05-21

## Context

Creative assets such as images, videos, thumbnails, references, and delivery files can be large. Returning or storing large binary files directly through MCP responses is inefficient and increases token and operational cost.

## Decision

Store assets outside the MCP server in an object storage or file system such as Cloudflare R2, S3, Google Drive, or another approved storage provider.

The MCP should return references, IDs, URLs, metadata, and summaries.

## Alternatives considered

- Return files directly through MCP responses: rejected due to size and token inefficiency.
- Store files in the database: rejected for scalability and cost.
- Store files externally and reference them: accepted.

## Consequences

This keeps MCP responses compact and makes asset delivery easier.

The tradeoff is that storage permissions, signed URLs, and lifecycle management must be designed.

## Impact on VOS Studio MCP

Asset-related tools should return structured references:

```json
{
  "asset_id": "asset_123",
  "storage_url": "...",
  "preview_url": "...",
  "metadata": {}
}
```
