# TASK-001 source-discovery findings

**Retrieval and verification date:** 2026-09-07  
**Scope:** Public Town of Ajax meeting records and official Town of Ajax YouTube meeting recordings.  
**Conclusion:** Proceed with a cautious connector based on the public OData meeting collection, deterministic normalization, and human-reviewed evidence for ambiguous documents, videos, and captions. Do not treat this spike as proof of production architecture.

## Sample matrix

| ID | Meeting | Official record | Variation verified |
|---|---|---|---|
| A | Council — Nov. 17, 2025 | [Record](https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses(f96faf0b-5876-f111-ab0e-3833c5fa4def)) | Regular Council baseline; agenda package, adopted minutes, direct video, automatic captions. |
| B | CAP — Nov. 3, 2025 | [Record](https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses(a27892d5-5776-f111-ab0e-3833c5fa4def)) | Community Affairs and Planning Committee type. |
| C | GGC — Dec. 8, 2025 | [Record](https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses(4db4ae62-5876-f111-ab0e-70a8a50cc0b4)) | GGC and companion Council record share YouTube video `BZAPz7ryBKE`. |
| D | Special Council — Aug. 11, 2026 | [Record](https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses(35ceda6a-c291-f111-8077-3833c5fa4def)) | Special Council type. |
| E | Committee of Adjustment — Mar. 25, 2026 | [Record](https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses(db736fcf-5976-f111-ab0e-70a8a50cc0b4)) | Quasi-judicial meeting; source title incorrectly says Mar. 23 Council; purported stream is an offline placeholder with no transcript. |
| F | Council — May 19, 2026 | [Record](https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses(0fa51ad4-5576-f111-ab0e-3833c5fa4def)) | Portal video link is blank; agenda field contains adopted minutes and minutes field contains draft minutes; official-channel video matched with reasons. |

Five available videos expose timestamped English automatic captions. They are useful for locating discussion but contain recognition errors and are not authoritative quotations or spelling. The March 25 placeholder is reported as unavailable, not as a successful extraction.

## Answers to the discovery questions

1. **Stable identifiers:** Each tested meeting entity has a UUID in `crf6e_cityconnectionsmeetingsid`. The prototype also creates a deterministic synthetic `local_id` when that UUID is absent.
2. **Date enumeration:** The collection accepts OData `$filter` bounds on `crf6e_meetingdate`, `$select`, and `$orderby`; browser automation is unnecessary. User dates are Ajax local dates and are converted to UTC boundaries so winter evening meetings are not shifted into the wrong day.
3. **Pagination and state:** Responses may expose `@odata.nextLink`, which the client follows with loop protection. No authentication or session state was required. GET with `Accept: application/json` worked; HEAD returned 406.
4. **Meeting types:** The sample includes Council, CAP, GGC, Special Council, and Committee of Adjustment. Exact raw labels are normalized but retained through title and provenance.
5. **Exceptional meetings:** `crf6e_meetingstatus` represents completed/cancelled state; November enumeration exposed a cancelled appeals meeting. Special meetings have a distinct type. Joint/consecutive streams are not represented structurally by the calendar record.
6. **Document links:** Agenda and minutes blob endpoints are stable per meeting UUID. The entity does not enumerate individual reports and attachments. Bounded PDF inspection found no embedded file attachments; it did find explicit document links in some packages, including public report/attachment links in sample D, and records them separately without recursive downloading.
7. **Revisions:** `modifiedon` and OData ETags show record changes, but the selected entity metadata does not expose a complete document-version history. Hashing retrieved bytes is recommended later.
8. **Document metadata:** Filenames, source-field role, record modification time, and URLs are available. Publication time, byte size, and authoritative adoption/revision status are generally absent.
9. **PDF quality:** All 12 top-level sample PDFs were inspected without committing their bytes. Eleven were text-based; sample A's 80-page agenda was mixed because 78 pages crossed the text threshold and two did not. None was malformed or wholly scanned.
10. **Draft versus adopted minutes:** Portal fields and filenames are not reliable enough. Sample F demonstrates two same-named minutes documents in misleading fields; reviewed evidence is required.
11. **Video linkage:** Some records link directly to YouTube; E and F have blank portal video fields.
12. **Video matching:** Direct links receive confidence 1.0. Independent matches require date/type/title reasons and remain warnings when confidence is below 0.80.
13. **Consecutive meetings:** Sample C records the shared video and companion Council source ID rather than assigning the stream exclusively to GGC.
14. **Captions:** Five sample videos had timestamped English ASR tracks; one scheduled placeholder had none. Automatic captions are unverified.
15. **Timestamp evidence:** Caption cues provide start times that can support later deep links, but transcript corpora are excluded from Git. This spike retains only availability metadata.
16. **Least-fragile access:** Public OData GET for meeting discovery, direct blob URLs for documents, and reviewed YouTube evidence for gaps.
17. **Operational behaviour:** The prototype implements bounded date ranges, explicit field selection, a descriptive user agent, three retry attempts with exponential backoff, pagination, and a 25 MiB per-PDF inspection limit. Development live checks were manually limited; persistent caching and automatic request-rate throttling are recommendations, not implemented features.
18. **Manual correction:** Wrong title/date, missing portal video, low-confidence video candidate, shared-stream boundaries, draft/adopted status, unavailable captions, and mislabeled fields.
19. **Break risks:** Renamed Dataverse fields/entity set, changed portal table permissions, altered OData pagination, document replacement without version metadata, YouTube title changes, and caption-delivery changes.
20. **Offline testing:** Yes. Sanitized metadata fixtures cover normalization, missing/unavailable sources, ambiguity, combined streams, synthetic identity, date filtering, and idempotent reruns with no network.

## Access and fragility notes

The portal's record JSON is the best discovery source found. Live enumeration uses `https://ajax-publicmeetings.powerappsportals.com/_api/crf6e_cityconnectionsmeetingses` with encoded `$select`, `$filter`, and `$orderby` query parameters. Direct document blob URLs work as retrieval targets, but a successful link does not prove correct classification. Sample E proves that title metadata can conflict with the typed meeting and scheduled date. Sample F proves that field names can conflict with document content. Package inspection is bounded and non-recursive: it records hashes, page/text metrics, and document-like link annotations while leaving linked-file retrieval to a later assignment.

YouTube transcript access is materially more fragile. Page metadata advertised caption tracks, but direct caption-track URLs returned HTTP 200 with empty bodies during preflight; a transcript client route succeeded for five videos. Any later connector needs retries, explicit unavailable/delayed/unknown states, and a review path. It must not treat ASR text as authoritative.

## Prototype schema notes

The TASK-001 example schema is preserved with these additions:

- `local_id` provides stable idempotent identity even without a source UUID;
- `source_modified_at` retains the portal's record modification time;
- document `source_field` makes field/content conflicts visible;
- document `pdf_inspection` records bounded page/text metrics, quality classification, and the count of document-like links;
- linked report and attachment annotations become document records whose `source_field` is `agenda_link` or `minutes_link`;
- video `availability`, `caption_kind`, and `shared_with_source_ids` preserve observed failure and shared-stream states; and
- the manifest envelope records schema version, requested date range, and meeting count.

## Blockers and next experiments

- Parse report boundaries inside consolidated agenda packages; explicit link annotations are now inventoried, but reports embedded as page ranges are not separate source files.
- Compare saved content hashes over time to characterize silent document replacement and revisions.
- Test a credential-free, policy-compliant YouTube channel enumeration method separately; keep manual review as the fallback.
- Determine combined-stream agenda boundaries before any transcript-to-item alignment work.
- Freeze a larger set containing cancelled, rescheduled, advisory, scanned-PDF, and missing-minutes records.

## Reproduction

See `spikes/source_discovery/README.md`. The committed sample manifest is generated from `meetings.json` plus the reviewed `evidence_index.json`. Offline tests use Python's standard library; `tzdata` is conditionally declared for Windows systems that do not ship the IANA timezone database.

No credentials, source PDFs, videos, captions, transcripts, cookies, sessions, bulk downloads, or private information are committed.
