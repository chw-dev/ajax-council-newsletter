# Ajax Council Newsletter — Data model

**Status:** Draft produced under approved TASK-002; awaiting product-owner acceptance  
**Scope:** Logical model for a private, single-user first release; no migration or implementation

## Modeling rules

- Stable logical entities are separated from immutable observations and versions.
- Every externally obtained value retains its raw form, source, retrieval time, and artifact identity where applicable.
- Normalized values are derived and versioned; they never erase raw values.
- Staff recommendations and Council decisions are different claim kinds.
- Draft minutes and adopted minutes are different reviewed authority states.
- Automatic speech recognition (ASR) and human-verified quotations are different evidence states.
- `unavailable` means an affirmative observation; `unknown` means insufficient observation.
- Human corrections are overlays with audit history, not destructive edits to source facts.
- Timestamps are UTC instants; meeting-local dates and timezone identifiers are also preserved.
- Primary keys are opaque UUIDs unless a content hash is explicitly the identity.

## Core source entities

### `meeting`

Required: `meeting_id`, `created_at`, `lifecycle_state`; optional observed identity includes portal UUID, committee, local start, and source title.
Unique non-null `(source_system, portal_uuid)`; fallback identity is a reviewed alias. Lifecycle is `discovered`, `active`, `cancelled`, `superseded`, `withdrawn`, or `unknown`; relationships are one-to-many except streams/documents.

### `source_snapshot`

Required: `snapshot_id`, `source_version_id`, `source_system`, `retrieved_at`, `payload_artifact_hash`, `payload_hash`, `schema_version`; optional scrubbed URL, ETag, last-modified, cursor.
Unique `(source_system, payload_hash)`; one snapshot has many observations and belongs to no mutable meeting state.

### `source_version` registry

Required: immutable `source_version_id`, `source_kind`, artifact hash or stable captured identity, `captured_at`, and subtype key; kinds are snapshot, document, stream media, transcript track, and derived text.
Each typed version has one registry row and unique FK; evidence/parser inputs reference it, never `(kind,id)`.
Locators resolve snapshots directly, documents through pages, transcripts through track/segments, and whole streams through stream versions.

### `meeting_observation`

Required: `observation_id`, `snapshot_id`, `meeting_id`, `field_name`, `raw_value_json`, `observed_at`; optional normalized value, rule/version, warning.
Unique `(snapshot_id, meeting_id, field_name)`; many observations belong to one meeting and snapshot.

### `document`

Required: `document_id`, canonical URL, role, created time, lifecycle; roles are agenda package/attachment, staff report, minutes, notice, other, unknown.
Original URL is observed; canonical source identity is unique per system, while identical bytes may share an artifact. Documents have many versions and meeting relationships.

### `document_version`

Required: `document_version_id`, unique FK `source_version_id`, `document_id`, artifact hash, retrieval time, media type, length; optional ETag, last-modified, filename, predecessor.
Unique `(document_id, artifact_hash)`; versions are immutable and replacements add successor edges.

### `document_authority_assessment`

Required: `assessment_id`, document version, authority state, basis, reason, reviewer, assessed time; states are draft, adopted, final non-minutes, unknown, disputed.
Optional predecessor and evidence. Assessments are immutable; corrections supersede, only the latest non-superseded is effective, and source labels never directly set authority.

### `stream`

Required: `stream_id`, platform/resource ID, created time, lifecycle; optional canonical URL, channel identity, title observation.
Unique known `(platform, platform_resource_id)`, otherwise reviewed URL identity; streams have many versions, tracks, and meeting relationships.

### `stream_observation`

Required: observation ID, stream ID, observed time, availability, and snapshot/provenance URL; optional title, duration, published time, diagnostic.
Availability is not checked, available, unavailable, delayed, restricted, error, or unknown; unavailable does not imply permanent absence.

### `stream_version`

Required: stream version ID, unique source-version FK, stream, observed time, and media hash/stable revision; optional artifact, duration, predecessor.
Unique `(stream_id, media_identity_hash)` when known; metadata observations remain distinct from captured versions.

## Relationships and parsed structure

### `meeting_document`

Required: relationship ID, meeting, document, role, basis, review; roles cover agenda, minutes, report, attachment, context.
Unique `(meeting_id, document_id, relationship_role)`; cardinality is many-to-many.

### `document_membership`

Required parent/child document IDs, membership role, discovered-from version; unique triple records explicit links without unbounded crawling.

### `meeting_stream`

Required: `meeting_stream_id`, `meeting_id`, `stream_id`, `basis`, `review_state`.
Optional: discovery confidence; reviewed boundaries never live on this mutable relationship.
Uniqueness: `(meeting_id, stream_id)`.
This is deliberately many-to-many.

### `meeting_stream_decision`

Required: `decision_id`, `meeting_stream_id`, `state`, `reviewer`, `decided_at`, `reason`.
Optional: start/end offsets, predecessor decision ID, and explicit prior/replacement value hashes.
Constraint: end exceeds start; one effective non-superseded decision per relationship.
Decisions are immutable and supersede additively, preserving every boundary and match correction.

### `parse_run`

Required: `parse_run_id`, FK `input_source_version_id`, `parser_name`, `parser_version`, `config_hash`, `state`, `created_at`.
State: `pending`, `running`, `succeeded`, `partial`, `failed_terminal`, `superseded`.
Uniqueness: `(input_source_version_id, parser_name, parser_version, config_hash)`.
Optional: output artifact hash, completeness code, bounded diagnostics.

### `document_page`

Required: `page_id`, `parse_run_id`, `page_number`, `text_artifact_hash`, `text_hash`.
Optional: width, height, extraction quality, OCR state.
Uniqueness: `(parse_run_id, page_number)`.

### `agenda_item`

Required: `agenda_item_id`, `meeting_id`, `source_document_version_id`, `ordinal_key`, `raw_heading`, `lifecycle_state`.
Optional: normalized number, title, parent agenda item, page range.
Uniqueness: `(source_document_version_id, ordinal_key)`.
A tree is represented by the optional self-reference; source order remains explicit.

### `transcript_track`

Required: `track_id`, unique FK `source_version_id`, `stream_version_id`, `origin`, `language`, `created_at`, `lifecycle_state`.
Origin: `platform_caption`, `automatic_asr`, `human_transcript`, `official_transcript`.
Optional: provider, model/version, config hash, artifact hash.
Uniqueness: stable input plus origin/provider/version/config.

### `transcript_segment`

Required: `segment_id`, `track_id`, `sequence`, `start_ms`, `end_ms`, `text`, `text_hash`.
Optional: speaker label, confidence, word-timing artifact hash.
Constraint: `0 <= start_ms < end_ms`; sequence unique within track.
ASR segments remain `automatic_unverified` regardless of confidence score.

### `alignment`

Required: `alignment_id`, `meeting_id`, `state`, `method`, plus exactly one target FK and one source FK.
Target FKs are explicit nullable `agenda_item_id` or `meeting_stream_id`; source FKs are explicit nullable `page_id` or `segment_id`.
Optional: interval/page bounds, confidence and explanation; review is an additive alignment decision.
State: `proposed`, `accepted`, `rejected`, `superseded`, `needs_review`.
Check constraints require exactly one FK in each side; uniqueness covers selected FK columns, bounds, and method version.

## Evidence and editorial entities

### `claim`

Required: stable `claim_id`, `meeting_id`, `claim_kind`, and `created_at`.
Kinds include `staff_recommendation`, `motion`, `council_decision`, `discussion`, `context`, `quotation_candidate`.
The logical claim contains no mutable claim text or review result.

### `claim_revision` and `claim_review_decision`

A revision requires `claim_revision_id`, `claim_id`, sequence, text, text hash, created time, provenance, and optional predecessor.
Uniqueness: `(claim_id, sequence)`; revisions are immutable and corrections append successors.
A review decision requires decision ID, exact claim revision ID, state, reviewer, time, reason, and optional predecessor decision.
Review states are `machine_proposed`, `human_accepted`, `human_rejected`, `needs_review`, and `superseded`.
Review corrections are additive; one latest non-superseded decision is effective per revision.
A recommendation may relate to a decision but cannot change kind into one.

### `claim_relation`

Required: exact `from_claim_revision_id`, exact `to_claim_revision_id`, `relation_kind`, `created_at`.
Kinds: `responds_to`, `adopts`, `amends`, `contradicts`, `clarifies`, `supersedes`.
Uniqueness: `(from_claim_revision_id, to_claim_revision_id, relation_kind)`.

### `evidence_reference`

Required: `evidence_id`, FK `claim_revision_id`, FK `source_version_id`, `locator_kind`, `support_role`, `created_at`.
Locators: page/region, document character span, transcript interval, or whole-source observation.
Support role: `supports`, `contradicts`, `contextualizes`, `authority_basis`.
Locator child tables use explicit FKs: snapshot locator to `snapshot_id`, page/region to `page_id`, transcript interval to `track_id` and optional `segment_id`, stream interval to `stream_version_id`.
A check plus one-to-one locator rows ensures exactly one locator matching the registered source kind.
Uniqueness: claim revision, source version, locator, and support role.

### `quote_verification`

Required: `verification_id`, `claim_revision_id`, `source_stream_version_id`, `start_ms`, `end_ms`, `verified_text`, `verifier`, `verified_at`.
Optional: notes and related transcript segment IDs.
Only an active verification can authorize quote styling.
Changing verified text creates a successor verification and audit event.

### `edition` and `edition_revision`

`edition` requires ID, coverage period, title, lifecycle, and creation time.
`edition_revision` requires revision ID, edition ID, sequence, content artifact hash, render-input hash, and creation time.
Uniqueness: `(edition_id, sequence)` and immutable content hash per revision.
Lifecycle: `draft`, `in_review`, `approved`, `superseded`, `withdrawn`.
An approved revision is immutable; edits create a later draft revision.

### `edition_claim`

Required: `edition_claim_id`, `edition_revision_id`, exact `claim_revision_id`, `section_key`, `position`, `presentation_state`.
Optional: editorial framing and uncertainty label.
Uniqueness: `(edition_revision_id, section_key, position)` and normally claim once per revision.

### `approval` and `export`

Approval requires ID, exact edition revision ID, actor, decision, timestamp, and content hash.
`approval_claim_resolution` freezes each included claim revision and its selected evidence IDs under that approval.
Its FKs target `approval`, `edition_claim`, `claim_revision`, and `evidence_reference`; constraints require the revision to equal edition membership.
Decision: `approved`, `rejected`, `revoked`; revocation is additive.
Export requires ID, approved revision ID, format, exporter version, artifact hash, and created time.
Formats in scope: `markdown`, `html`.
Uniqueness: approved revision, format, exporter version, and render configuration hash.

### `reconciliation`

Required: `reconciliation_id`, `meeting_id`, FK `trigger_source_version_id`, `state`, `created_at`.
State: `pending`, `compared`, `needs_review`, `accepted`, `dismissed`.
Findings link affected claims and prior edition revisions to later minutes or revised sources.
Reconciliation never mutates an historical approved edition.

## Jobs, provenance, and audit

`job` requires type, explicit nullable target FKs, generation, idempotency key, state, priority, creation time, input fingerprint, and config version.
Allowed targets are explicit meeting, document, stream, source version, edition revision, or reconciliation FKs; a check requires exactly one.
Job states are `pending`, `running`, `retry_wait`, `needs_review`, `succeeded`, `failed_terminal`, `cancelled`.
Idempotency is unique over operation fingerprint and generation; automatic retries stay in the same generation and job.
After `needs_review` or `failed_terminal`, an operator decision with a unique retry nonce creates generation N+1; terminal jobs never reopen in place.
A lease owner and expiry support `running -> pending` recovery; resume uses committed checkpoints and the same job generation.
`job_attempt` requires job ID, attempt number, start/end, outcome, retry class, and bounded diagnostic.
Attempt number is unique per job; retries never replace earlier attempts.
`provenance_event` records tool/rule version, config hash, and timestamp; input FKs target `source_version` or `claim_revision`, and output FKs target `source_version`, `claim_revision`, or `edition_revision`, with exactly-one checks.
Every derived artifact or normalized fact has at least one provenance event.
`manual_override` requires one explicit target FK (meeting observation, authority assessment, meeting-stream relationship, alignment, or claim revision), field, prior value, replacement, reason, actor, timestamp, and state.
Override state is `active`, `reversed`, or `superseded`; reversal references the earlier override.
`audit_event` is append-only and records action, actor, entity, timestamp, correlation ID, and before/after hashes.

## Retention and deletion semantics

Source versions, evidence, approved revisions, exports, approvals, overrides, and audits are append-only; withdrawal hides without breaking references.
Artifacts reachable from evidence, approval, export, reconciliation, or active parse output are retained; GC removes only unreferenced artifacts after grace and verified backup.
Deletion logs policy, actor, time, hash, reachability proof, and outcome; incomplete temporary downloads may be removed because they never became artifacts.
A required privacy purge tombstones identities and records broken-evidence impact; database and artifact backups share a reproducible checkpoint manifest.

## Scenario walkthroughs

| Scenario | Records and relationships | Required semantic result |
|---|---|---|
| A — baseline Council | Meeting, agenda/minutes documents and versions, direct stream link, track, items, claims, evidence | Adopted status is reviewed; reruns reuse keys; new bytes make successors |
| B — alternate committee | Same meeting model with raw type observation and normalized committee value | No Council-only branch; unknown committee types remain reviewable |
| C — shared stream | One stream, two meetings, two `meeting_stream` rows, reviewed boundaries | Many-to-many is preserved; segments remain stream-owned |
| D — explicit report links | Agenda package plus child report documents and membership edges | Each linked file is separately versioned and citable; no implicit crawl |
| E — wrong title/unavailable/no transcript | Conflicting observations, unavailable stream observation, review task; no track | Wrong title does not replace typed/date identity; unknown is not asserted as unavailable |
| F — blank video/mislabeled agenda-minutes | Blank portal observation, reviewed external stream match, separate minute versions and authority reviews | Match is audited; field label cannot promote draft minutes to adopted |

## Required database constraints

- Foreign keys are enabled and checked on every connection.
- Content hashes use a single lowercase SHA-256 representation.
- Immutable tables reject update/delete through repository policy and invariant tests.
- Partial unique indexes enforce uniqueness only when external identifiers are non-null.
- Check constraints enforce ranges, enum values, and locator completeness.
- Approved revision hashes must equal the revision named by approval.
- Evidence cannot reference mutable logical entities without a specific version or snapshot.
- Verified quotations require an active `quote_verification`; ASR confidence is insufficient.
- Manual effective values are resolved as views/projections over observations plus active overrides.
