# Ajax Council Newsletter

Private, evidence-first tooling for turning the public record of Town of Ajax formal meetings into accessible local-news reporting.

## Current status

The TASK-001 source-discovery prototype is implemented, accepted, and merged into `main`. `TASK-002` is designing the production architecture and data model; it does not authorize production implementation.

The project is governed by the approved *Ajax Council Newsletter Project Charter 1.0*. Human editorial approval is required before any newsletter is exported or published.

## Design documents

- [`SOURCE_DISCOVERY.md`](SOURCE_DISCOVERY.md) records the TASK-001 source findings and failure cases.
- [`ADR-0001-source-access.md`](ADR-0001-source-access.md) records the discovery-spike access decision.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) defines the proposed production component boundaries and control flow.
- [`DATA_MODEL.md`](DATA_MODEL.md) defines the proposed entities, relationships, lifecycle states, and provenance contracts.
- [`ADR-0002-persistence-and-artifact-storage.md`](ADR-0002-persistence-and-artifact-storage.md) records the proposed persistence and artifact-storage decision.

## Repository controls

- `main` is the default branch. Its protection requirement is covered by the formally accepted, documented exception in issue #1.
- Agents must not commit directly to `main`; each approved assignment uses one issue, one branch, and one pull request.
- `TASK-001` is tracked in issue #1; `TASK-002` is tracked in issue #3 and uses `task/002-architecture-data-model`.
- The repository-preflight workflow checks required safeguards, prohibited tracked paths, common secret patterns, and the deterministic source-discovery tests.
- The branch-protection exception must be reconsidered before collaborators are added, production or publication capabilities are introduced, or the repository moves to an eligible organization account.

## Local configuration

Local configuration uses an untracked `.env` file:

```sh
cp .env.example .env
```

Add only local values to `.env`. Never commit credentials, tokens, cookies, session data, or private identifiers. When a new setting is required, document its variable name with a safe placeholder in `.env.example`.

## Local and generated data

Keep the following outside Git:

- credentials and local configuration;
- raw or bulk meeting-document downloads;
- downloaded videos and caption files;
- generated transcripts;
- local caches, logs, and temporary files.

Small, sanitized fixtures may be committed under `fixtures/` only when an approved assignment requires them and automated tests can run without live credentials.

## Scope boundary

Implementation remains limited to the accepted `TASK-001` source-discovery spike. TASK-002 adds design documents only. Newsletter generation, user-interface code, production databases, deployment, authentication, and publication integrations remain unstarted.
