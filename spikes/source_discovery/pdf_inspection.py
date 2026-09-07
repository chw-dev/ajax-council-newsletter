"""Bounded PDF inspection for linked public records in Ajax meeting packages."""

from __future__ import annotations

import hashlib
import io
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .discovery import DiscoveryError, USER_AGENT

DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


def classify_link(url: str) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    decoded_path = unquote(parsed.path)
    suffix = PurePosixPath(decoded_path).suffix.lower()
    report_path = "/report" in decoded_path.lower()
    attachment_path = "att-" in decoded_path.lower() or "/reference documents/" in decoded_path.lower()
    if suffix not in DOCUMENT_EXTENSIONS and not report_path and not attachment_path:
        return None
    title = PurePosixPath(decoded_path).name or parsed.netloc
    lower = title.lower()
    kind = "attachment" if attachment_path or lower.startswith(("att-", "appendix")) else "report" if report_path else "other"
    status = "draft" if "draft" in lower else "revised" if "revised" in lower or "amended" in lower else "unknown"
    return {"kind": kind, "status": status, "title": title, "url": url}


def inspect_pdf_bytes(content: bytes) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise DiscoveryError("PDF inspection requires pypdf; install requirements.txt") from exc
    try:
        reader = PdfReader(io.BytesIO(content))
        text_counts: list[int] = []
        links: dict[str, dict[str, Any]] = {}
        for page in reader.pages:
            text_counts.append(len((page.extract_text() or "").strip()))
            for annotation_ref in page.get("/Annots") or []:
                annotation = annotation_ref.get_object()
                action = annotation.get("/A") or {}
                uri = action.get("/URI") if annotation.get("/Subtype") == "/Link" else None
                if uri:
                    classified = classify_link(str(uri))
                    if classified:
                        links[classified["url"]] = classified
        text_pages = sum(count >= 40 for count in text_counts)
        if text_pages == len(text_counts):
            quality = "text"
        elif text_pages == 0:
            quality = "scanned"
        else:
            quality = "mixed"
        return {
            "pdf_quality": quality,
            "page_count": len(text_counts),
            "text_page_count": text_pages,
            "text_character_count": sum(text_counts),
            "linked_document_count": len(links),
            "linked_documents": [links[url] for url in sorted(links)],
            "content_hash": f"sha256:{hashlib.sha256(content).hexdigest()}",
        }
    except (PdfReadError, KeyError, TypeError, ValueError) as exc:
        return {
            "pdf_quality": "malformed",
            "page_count": None,
            "text_page_count": None,
            "text_character_count": None,
            "linked_document_count": 0,
            "linked_documents": [],
            "content_hash": f"sha256:{hashlib.sha256(content).hexdigest()}",
            "inspection_error": str(exc),
        }


def retrieve_pdf(
    url: str,
    max_bytes: int = 25 * 1024 * 1024,
    timeout: float = 30.0,
    opener: Callable[..., Any] = urlopen,
) -> bytes:
    request = Request(url, headers={"Accept": "application/pdf", "User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise DiscoveryError(f"PDF exceeds configured {max_bytes}-byte limit")
            content = response.read(max_bytes + 1)
    except DiscoveryError:
        raise
    except Exception as exc:
        raise DiscoveryError(f"Unable to retrieve public PDF {url}: {exc}") from exc
    if len(content) > max_bytes:
        raise DiscoveryError(f"PDF exceeds configured {max_bytes}-byte limit")
    if not content.startswith(b"%PDF-"):
        raise DiscoveryError("Document response is not a PDF")
    return content


def inspect_records(records: list[dict[str, Any]], max_bytes: int = 25 * 1024 * 1024) -> dict[str, Any]:
    meetings: dict[str, Any] = {}
    for raw in records:
        source_id = raw.get("crf6e_cityconnectionsmeetingsid")
        if not source_id:
            continue
        document_overrides: dict[str, Any] = {}
        for field, url_field in (("agenda", "crf6e_agendalink"), ("minutes", "crf6e_minuteslink")):
            url = raw.get(url_field)
            if not url:
                continue
            try:
                inspection = inspect_pdf_bytes(retrieve_pdf(str(url), max_bytes=max_bytes))
                document_overrides[field] = {
                    "content_hash": inspection.pop("content_hash"),
                    "pdf_inspection": inspection,
                }
            except DiscoveryError as exc:
                document_overrides[field] = {"inspection_error": str(exc)}
        meetings[str(source_id)] = {"document_overrides": document_overrides}
    return {"meetings": meetings}


def merge_evidence(base: dict[str, Any], addition: dict[str, Any]) -> dict[str, Any]:
    merged = {**base, "meetings": {**base.get("meetings", {})}}
    for source_id, new_meeting in addition.get("meetings", {}).items():
        old_meeting = merged["meetings"].get(source_id, {})
        combined = {**old_meeting, **new_meeting}
        document_overrides = {**old_meeting.get("document_overrides", {})}
        for field, details in new_meeting.get("document_overrides", {}).items():
            previous = {**document_overrides.get(field, {})}
            if details.get("inspection_error"):
                previous.pop("content_hash", None)
                previous.pop("pdf_inspection", None)
            else:
                previous.pop("inspection_error", None)
            document_overrides[field] = {**previous, **details}
        combined["document_overrides"] = document_overrides
        merged["meetings"][source_id] = combined
    return merged
