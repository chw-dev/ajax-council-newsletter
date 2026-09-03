# Ajax Council Newsletter

Private, evidence-first tooling for turning the public record of Town of Ajax formal meetings into accessible local-news reporting.

## Current status

Repository preflight for `TASK-001` is complete. The source-discovery prototype has **not** started.

The project is governed by the approved *Ajax Council Newsletter Project Charter 1.0*. Human editorial approval is required before any newsletter is exported or published.

## Repository controls

- `main` is the protected default branch.
- Each approved assignment uses one issue, one branch, and one pull request.
- `TASK-001` uses `task/001-source-discovery`.
- The repository-preflight workflow checks required safeguards, prohibited tracked paths, and common secret patterns.
- Prototype-specific tests, linting, and type checks must be added when the implementation stack is selected.

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

Repository setup is the only completed work. Newsletter generation, user-interface code, production databases, deployment, authentication, publication integrations, and the `TASK-001` source-discovery prototype remain unstarted.
