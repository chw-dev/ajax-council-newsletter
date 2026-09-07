# ADR-0002: Persistence and artifact storage

**Status:** Proposed; awaiting product-owner acceptance  
**Date:** 2026-09-07  
**Decision owner:** Product owner  
**Scope:** Private, single-user Ajax Council Newsletter first release

## Context

The workflow discovers public meeting metadata, captures changing documents and media references, parses source material, aligns meetings with streams and agenda items, records evidence, drafts a newsletter, requires human approval, exports Markdown and HTML, and later reconciles published claims with adopted minutes.

The data has two very different shapes.
Metadata is relational, small, frequently queried, and transaction-sensitive.
Artifacts are immutable byte sequences that may be large: source payloads, PDFs, captions, transcripts, extracted text, drafts, and exports.

The first release is operated privately by one product owner on one machine.
It does not need a network service, multi-user authorization, or elastic scale.
It does need reliable restart after interruption, deterministic reruns, evidence provenance, and conservative retention.

Public source labels can be wrong or late.
A minutes field can contain a draft or a misleading filename.
A portal video field can be blank while an official stream exists elsewhere.
One stream may cover multiple meetings.
Therefore persistence must retain observations and reviewed interpretations separately.

## Decision drivers

1. Preserve exact source bytes and all evidence used in an approved edition.
2. Make ingestion and derivation idempotent, retryable, and resumable.
3. Support relational constraints and many-to-many meeting/stream relationships.
4. Keep deployment and backup understandable for a single operator.
5. Avoid storing large binary content in database pages.
6. Permit deterministic offline tests with temporary storage roots.
7. Provide a credible path to multi-process or hosted operation if demand emerges.
8. Prevent Git history from becoming an artifact or private editorial store.

## Decision

Use SQLite in WAL mode for metadata and a content-addressed local filesystem for artifacts.

The SQLite database is stored under a configured application data root outside the Git repository.
It contains logical entities, immutable version records, relationships, job state, provenance, manual overrides, approvals, export records, and audit events.

The artifact store is also under the configured data root and outside Git.
Each artifact is addressed by the lowercase SHA-256 digest of its exact bytes.
A representative layout is `artifacts/sha256/ab/cd/<full-hash>`.
The exact path convention is an implementation detail, but identity by full digest is not.

SQLite rows refer to artifacts by hash, byte length, and media type.
Large bytes are not stored as database BLOBs.
Two source URLs with identical bytes share an artifact while retaining separate source and version records.

Enable WAL journaling, foreign keys, a bounded busy timeout, and explicit transactions.
Use one application writer at a time in the first release.
Concurrent readers are allowed.
Long-running fetch and parse work happens outside write transactions.

## Write protocol

1. Stream incoming bytes to a temporary file inside the artifact filesystem.
2. Enforce configured byte and time limits while streaming.
3. Calculate SHA-256 and byte length from the streamed bytes.
4. Flush, durably sync, and close the temporary file.
5. If the digest path exists, read and hash every byte; reuse it only when full SHA-256 and length match.
6. Quarantine a mismatching digest target as an integrity incident; never overwrite or trust it.
7. Otherwise atomically rename the temporary file to the digest path without replacing an existing target.
8. Durably sync the final file and its parent directory, then open a short metadata transaction.
9. Insert or reuse the artifact row and immutable `source_version` registry/subtype rows; append provenance and job result.
10. Commit, then remove any remaining temporary file.

A crash before rename leaves only a removable temporary file.
A crash after rename but before database commit may leave an unreferenced complete artifact.
An integrity sweep can hash, register, or quarantine that orphan.
A database row must never be committed before the final artifact and directory entry are durably persisted.
If a platform cannot provide portable file and parent-directory sync, ingest is deferred or routed through a documented storage adapter with equivalent durability; mere readability is not sufficient.

## Metadata transaction policy

Discovery commits bounded response pages rather than a whole date range.
Acquisition commits one immutable version at a time.
Parse outputs are staged before a short result transaction.
Review decisions and their audit events commit together.
Edition approval names an exact immutable revision and content hash.
Export reads only that approved revision and records the resulting artifact hash.

Jobs use durable states and unique generation-scoped idempotency keys.
The fingerprint covers operation type, an enforceable target FK, immutable inputs, tool/config versions, and parameters; generation is appended to the key.
Automatic retries append attempts in one generation, and lease expiry returns `running` to `pending` at its committed checkpoint.
`needs_review` and `failed_terminal` never reopen: an operator decision and unique retry nonce create generation N+1 idempotently.

## Backup and restore

Database and artifacts form one logical dataset.
A valid backup captures a quiesced SQLite checkpoint, the reachable artifact tree, and a manifest connecting them.
The manifest records backup time, schema version, database hash, artifact count, and reachable hashes or a verifiable inventory digest.

Restore verification runs SQLite integrity checks, foreign-key checks, and artifact reachability/hash checks.
Missing evidence bytes are reported as an integrity failure.
They are not silently replaced by newly downloaded bytes.
Reacquisition, when possible, creates a new observation and is compared with the missing identity.

WAL sidecar files are handled through SQLite's supported backup/checkpoint procedure.
Copying only the main database while writes are active is not an accepted backup.

## Security and trust boundaries

The data root should use owner-only permissions where supported.
Credentials and cookies are never persisted in SQLite, artifact names, URLs, or logs.
Token-bearing URLs are scrubbed before metadata persistence.
Raw artifacts are treated as untrusted input.
Parsers receive bounded files and do not determine editorial authority.

Git stores application code, schemas, design documents, sanitized fixtures, and deterministic expected outputs.
Git does not store captured public artifacts, raw media, credentials, private editorial drafts, operational logs, or generated editions awaiting publication.

Content addressing proves byte identity, not truth, authorship, official status, or safety.
Those properties remain modeled as sourced observations and reviewed decisions.

## Options considered

### Option A — SQLite WAL plus content-addressed local artifacts

Benefits:

- No server administration or network dependency.
- ACID metadata changes, foreign keys, indexes, and relational queries.
- WAL permits readers during short writes.
- Natural fit for one writer and modest first-release volume.
- Large artifacts remain streamable and independently hash-verifiable.
- Temporary directories make offline integration tests deterministic.
- Backup remains conceptually simple when database and artifact manifest are coordinated.

Costs and risks:

- Multiple concurrent writers require discipline and are not a scaling strategy.
- Database/artifact consistency spans two storage mechanisms.
- Local disk loss requires tested backups.
- Shared remote operation is awkward without a single service owner.

This option best matches current needs and is selected.

### Option B — PostgreSQL plus object storage

Benefits:

- Strong multi-writer concurrency and operational query tooling.
- Server-side access controls and remote clients.
- Object storage supplies scalable capacity, lifecycle rules, and durable replication.
- Better foundation for hosted workers and multiple reviewers.

Costs and risks:

- Requires two managed services, credentials, network availability, migrations, and coordinated backup policy.
- Local development and deterministic tests become more complex.
- Object creation and relational commit still require an application-level consistency protocol.
- Operational burden is disproportionate for one private user.

This option is deferred, not rejected permanently.

### Option C — Filesystem-only metadata and artifacts

Benefits:

- Minimal dependencies and human-readable manifests.
- Easy direct inspection and copying.
- Content-addressed files work naturally.

Costs and risks:

- Referential integrity and uniqueness become application conventions.
- Atomic updates across meetings, jobs, evidence, and approvals are difficult.
- Querying many-to-many shared streams and provenance requires custom indexing.
- Retry leases, audit history, and schema evolution become fragile.
- Concurrent review/export reads risk observing partially updated manifests.

This option is rejected for primary metadata.
Small sidecar manifests may aid inspection but cannot be authoritative.

## Consequences

The schema must distinguish logical identity from immutable versions and claim revisions.
An immutable `source_version` registry gives evidence and parser inputs one enforceable FK; typed locator rows resolve snapshots, document pages, transcript segments, or whole stream versions.
Parse, alignment, provenance, override, reconciliation, and job targets use explicit foreign keys and exactly-one checks, not polymorphic `(kind, id)` pairs.
Evidence, edition membership, and approval resolution name exact claim revisions; human review decisions are additive.
Supersession is additive.
Approved edition revisions remain immutable.
Manual overrides and reversals are audited.

Staff recommendations cannot be overwritten by Council decisions.
Draft/adopted status lives in immutable superseding authority assessments with reviewer, time, basis, reason, and evidence, never on document versions.
Meeting/stream boundaries live in superseding decisions that retain reviewer, time, reason, prior, and replacement values.
ASR text cannot be styled as a verified quotation without a verification record.
An affirmative unavailable observation remains distinct from not checked or unknown.

Artifact garbage collection must begin from database reachability.
Any artifact referenced by evidence, approvals, exports, reconciliation, active versions, or required audit provenance is retained.
Deletion is policy-driven, logged, and never based solely on age.

## Migration triggers

Reassess PostgreSQL plus object storage when one or more of these conditions persist:

- More than one writer or reviewer needs concurrent remote access.
- Write-lock contention or queue latency exceeds an agreed service objective.
- Processing moves to multiple machines or independently deployed workers.
- Local artifact volume exceeds reliable backup/restore windows or disk capacity.
- Availability requirements demand replicated storage and automated failover.
- Organization-wide authentication, authorization, or audit controls become required.
- Operational analytics or integrations need supported remote SQL access.

Threshold values are measured before migration; technology preference alone is not a trigger.

## Migration path

1. Keep repository interfaces independent of SQLite-specific row behavior.
2. Use opaque application UUIDs and portable scalar types in the logical model.
3. Maintain ordered, forward-only schema migrations and fixture-based conformance tests.
4. Quiesce writes and record a database/artifact checkpoint manifest.
5. Create the PostgreSQL schema with equivalent keys, constraints, states, and audit invariants.
6. Copy metadata in dependency order while preserving IDs and timestamps.
7. Upload each artifact by hash to object storage and verify digest and byte length.
8. Replace local paths with storage keys derived from the same content hash.
9. Run row-count, foreign-key, uniqueness, reachability, and evidence-resolution checks.
10. Shadow-read representative editions and compare rendered hashes where deterministic.
11. Cut over writers only after verification; retain the local checkpoint for rollback.
12. Record the new deployment decision in a successor ADR.

Object storage must support immutable-key semantics or conditional creation.
Database rows continue to reference content identity, not expiring signed URLs.
The dual-write period, if used, is bounded and reconciled from an explicit migration ledger.

## Deterministic test seams

Tests create a temporary SQLite database and artifact root per case.
The clock, UUID source, network connector, parser version, and retry scheduler are injected.
Golden fixtures pin input hashes and expected records.
Crash tests stop between temporary write, rename, metadata insert, and commit.
Recovery tests prove orphan handling, lease expiry, retry idempotency, and unchanged approved revisions.
Conformance tests are designed to run against a later PostgreSQL repository without changing domain expectations.

## Next small assignments

1. Define the initial SQLite schema and forward-only migration convention from `DATA_MODEL.md`.
2. Implement and test atomic content-addressed ingest plus integrity scanning.
3. Add job leasing, idempotency, retry classification, and resume tests.
4. Add backup manifest generation and restore verification as a separate bounded task.
5. Keep discovery/acquisition adaptation separate from persistence foundation review.

These are proposals for later approval.
This ADR authorizes no implementation, dependency, migration, or external write.
