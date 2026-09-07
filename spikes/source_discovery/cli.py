"""Command-line entry point for TASK-001 source discovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .discovery import DiscoveryError, discover, fetch_live, load_json, parse_date


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover and normalize public Town of Ajax meeting records.")
    parser.add_argument("--start", required=True, help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Inclusive end date (YYYY-MM-DD)")
    parser.add_argument("--fixture", help="Offline OData JSON fixture; omit for the live Ajax source")
    parser.add_argument("--evidence-index", help="Optional reviewed document/video evidence JSON")
    parser.add_argument("--inspect-pdfs", action="store_true", help="Download and inspect top-level PDFs for quality and linked documents")
    parser.add_argument("--max-pdf-bytes", type=int, default=25 * 1024 * 1024, help="Per-document download limit for --inspect-pdfs")
    parser.add_argument("--output", default="-", help="Output JSON path, or - for stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start = parse_date(args.start)
        end = parse_date(args.end)
        evidence = load_json(args.evidence_index) if args.evidence_index else {}
        if args.fixture:
            payload = load_json(args.fixture)
            records = payload.get("value")
            if not isinstance(records, list):
                raise DiscoveryError("Fixture must contain an OData value array")
            discovered_at = payload.get("retrieved_at")
        else:
            records = fetch_live(start, end)
            discovered_at = None
        if args.inspect_pdfs:
            from .pdf_inspection import inspect_records, merge_evidence

            evidence = merge_evidence(evidence, inspect_records(records, max_bytes=args.max_pdf_bytes))
        manifest = discover(records, start, end, evidence, discovered_at=discovered_at)
        rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if args.output == "-":
            sys.stdout.write(rendered)
        else:
            Path(args.output).write_text(rendered, encoding="utf-8")
        return 0
    except DiscoveryError as exc:
        print(f"source-discovery: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
