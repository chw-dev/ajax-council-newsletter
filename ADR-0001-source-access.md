# ADR-0001: Source access for the discovery spike

- **Status:** Proposed for TASK-001 review
- **Date:** 2026-09-07

## Decision

Use the Town of Ajax public Power Pages OData endpoint as the primary meeting enumerator. Interpret command dates in `America/Toronto`, convert the local-day boundaries to UTC for the OData filter, and use an explicit field selection, a descriptive user agent, retry/backoff, and OData `@odata.nextLink` pagination. Normalize the response deterministically and preserve the entity URL, source UUID, source modification time, document URLs, and warnings.

Inspect top-level agenda and minutes PDFs with a strict per-file size limit. Record their content hash and text/scanned/mixed/malformed quality, and enumerate document-like HTTP link annotations without recursively downloading them. Missing documents and inspection failures remain warnings.

Use direct video links from the meeting record when present. Keep independently reviewed YouTube matches and transcript observations in a separate evidence index. Never turn a missing portal link into an automatic high-confidence match. A shared stream must list every known meeting relationship, and confidence must include reasons.

Automated tests use small sanitized JSON fixtures and never contact live services.

## Why

The collection endpoint supports server-side date filtering and stable entity UUIDs without executing the public portal's JavaScript. This is smaller and less fragile than browser automation. It also exposes malformed records that a connector must not paper over, including a title/date conflict and mislabeled document fields in the approved sample.

Video and caption discovery is less stable. Some portal records omit a video; one stream covers consecutive meetings; a scheduled-stream placeholder is not playable; and automatic-caption delivery methods behave inconsistently. Separating reviewed evidence from raw discovery keeps those uncertainties visible.

## Alternatives considered

1. **Scrape the rendered meeting-calendar HTML.** Rejected as the primary method because the page is script-driven and adds presentation-layer fragility without improving source identity.
2. **Use browser automation.** Rejected for the spike because the public JSON source is sufficient for calendar discovery and automation would be slower and harder to test offline.
3. **Use the YouTube Data API as a required source.** Deferred because it requires credentials and quotas. TASK-001 must work without private credentials.
4. **Infer video matches silently from titles.** Rejected because missing links, corrupted titles, and combined streams make false matches plausible.

## Consequences

- Live meeting discovery needs no credentials.
- GET requests are supported; HEAD requests may return HTTP 406 and are not used as an availability test.
- Document metadata is limited. The meeting entity does not enumerate individual staff reports and attachments; the PDF inspector can enumerate explicit document links, while reports embedded as pages remain part of the package.
- Document adoption/revision status may require reviewed evidence or content comparison; filename and portal field name alone are insufficient.
- YouTube matching and transcript availability remain explicit, reviewable evidence rather than facts inferred by the calendar parser.
- Source-field changes, OData access-policy changes, caption-delivery changes, and revised PDFs are the principal connector break risks.
