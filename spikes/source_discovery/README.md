# Ajax source-discovery prototype

This bounded TASK-001 command discovers public Town of Ajax meeting records for an inclusive date range and writes a normalized JSON manifest. It requires Python 3.10 or newer. Install the small dependency set first:

```sh
python -m pip install -r requirements.txt
```

Run deterministically against the six sanitized sample records:

```sh
python -m spikes.source_discovery.cli \
  --start 2025-11-03 \
  --end 2026-08-11 \
  --fixture fixtures/source_discovery/meetings.json \
  --evidence-index fixtures/source_discovery/evidence_index.json \
  --output /tmp/ajax-sample-manifest.json
```

Run against the current public Ajax OData endpoint:

```sh
python -m spikes.source_discovery.cli \
  --start 2026-08-01 \
  --end 2026-08-31 \
  --inspect-pdfs
```

Live mode discovers calendar records and direct document/video links. `--inspect-pdfs` downloads only the top-level agenda and minutes PDFs, subject to a 25 MiB per-file limit, records text/scanned/mixed/malformed quality, computes a SHA-256 hash, and enumerates document-like link annotations without recursively downloading them. It deliberately leaves transcript status and independently matched videos as `unknown` unless a reviewed evidence index is supplied. This prevents the program from silently guessing where the portal has missing or corrupted metadata.

Run the offline tests:

```sh
python -m unittest discover -s tests -v
```

The committed fixtures contain metadata only: no PDFs, captions, transcripts, cookies, credentials, or private information.
