"""Deterministic discovery and normalization for public Ajax meeting records."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_ROOT = "https://ajax-publicmeetings.powerappsportals.com/_api"
ENTITY_SET = "crf6e_cityconnectionsmeetingses"
SELECT_FIELDS = (
    "crf6e_cityconnectionsmeetingsid",
    "crf6e_title",
    "crf6e_meetingtype",
    "crf6e_meetingdate",
    "crf6e_meetingstatus",
    "crf6e_agendalink",
    "crf6e_minuteslink",
    "crf6e_meetinglink",
    "crf6e_meetingagenda_name",
    "crf6e_meetingreference_name",
    "modifiedon",
)
USER_AGENT = "ajax-council-newsletter-source-discovery/0.1 (+public-record-research)"
AJAX_TIMEZONE = ZoneInfo("America/Toronto")


class DiscoveryError(RuntimeError):
    """Raised when a source cannot be read or normalized safely."""


@dataclass
class JsonHttpClient:
    timeout: float = 20.0
    attempts: int = 3
    backoff_seconds: float = 0.5
    opener: Callable[..., Any] = urlopen

    def get(self, url: str) -> dict[str, Any]:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                retryable = not isinstance(exc, HTTPError) or exc.code in {408, 429, 500, 502, 503, 504}
                if not retryable or attempt + 1 == self.attempts:
                    break
                time.sleep(self.backoff_seconds * (2**attempt))
        raise DiscoveryError(f"Unable to retrieve public Ajax source: {last_error}") from last_error


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DiscoveryError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def build_collection_url(start: date, end: date) -> str:
    if start > end:
        raise DiscoveryError("Start date must not be after end date")
    local_start = datetime.combine(start, datetime_time.min, tzinfo=AJAX_TIMEZONE)
    local_end = datetime.combine(end + timedelta(days=1), datetime_time.min, tzinfo=AJAX_TIMEZONE)
    utc_start = local_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    utc_end = local_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = urlencode(
        {
            "$select": ",".join(SELECT_FIELDS),
            "$filter": (
                f"crf6e_meetingdate ge {utc_start} and "
                f"crf6e_meetingdate lt {utc_end}"
            ),
            "$orderby": "crf6e_meetingdate asc",
        }
    )
    return f"{API_ROOT}/{ENTITY_SET}?{query}"


def fetch_live(start: date, end: date, client: JsonHttpClient | None = None) -> list[dict[str, Any]]:
    client = client or JsonHttpClient()
    url: str | None = build_collection_url(start, end)
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    while url:
        if url in seen:
            raise DiscoveryError("OData pagination loop detected")
        seen.add(url)
        payload = client.get(url)
        value = payload.get("value")
        if not isinstance(value, list):
            raise DiscoveryError("Ajax response did not contain an OData value array")
        records.extend(item for item in value if isinstance(item, dict))
        next_link = payload.get("@odata.nextLink")
        url = next_link if isinstance(next_link, str) and next_link else None
    return records


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"Unable to read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DiscoveryError(f"JSON file {path} must contain an object")
    return value


def _normalized_type(value: Any) -> str:
    text = " ".join(str(value or "unknown").split()).strip()
    aliases = {
        "community affairs and planning committee": "community_affairs_and_planning_committee",
        "general government committee": "general_government_committee",
        "special council": "special_council",
        "council": "council",
        "committee of adjustment": "committee_of_adjustment",
    }
    return aliases.get(text.lower(), re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unknown")


def _normalized_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "cancel" in text:
        return "cancelled"
    if text in {"complete", "completed", "closed"}:
        return "completed"
    if text in {"scheduled", "upcoming", "open"}:
        return "scheduled"
    return "unknown"


def _local_id(source_id: Any, title: str, scheduled_start: Any) -> str:
    if source_id:
        return f"ajax:{source_id}"
    seed = f"{scheduled_start or ''}|{' '.join(title.lower().split())}"
    return f"ajax:synthetic:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"


def _document_kind(title: str, source_field: str) -> str:
    lower = title.lower()
    if "minute" in lower:
        return "minutes"
    if "agenda package" in lower:
        return "agenda_package"
    if "agenda" in lower:
        return "agenda"
    if "report" in lower:
        return "report"
    if "attachment" in lower or "appendix" in lower:
        return "attachment"
    return "agenda" if source_field == "agenda" else "minutes" if source_field == "minutes" else "other"


def _document_status(title: str) -> str:
    lower = title.lower()
    if "draft" in lower:
        return "draft"
    if "revised" in lower or "amended" in lower:
        return "revised"
    if "adopted" in lower or "approved" in lower or "final" in lower:
        return "adopted"
    return "unknown"


def _youtube_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"live", "embed", "shorts"}:
            return parts[1]
    return None


def _title_date(title: str) -> date | None:
    match = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", title)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def _documents(raw: dict[str, Any], evidence: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    pairs = [
        ("agenda", raw.get("crf6e_meetingagenda_name"), raw.get("crf6e_agendalink")),
        ("minutes", raw.get("crf6e_meetingreference_name"), raw.get("crf6e_minuteslink")),
    ]
    for extra in raw.get("documents", []):
        if isinstance(extra, dict):
            pairs.append((str(extra.get("source_field", "additional")), extra.get("title"), extra.get("url")))
    overrides = evidence.get("document_overrides", {})
    result: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for source_field, title_value, url_value in pairs:
        if not url_value:
            if source_field in {"agenda", "minutes"}:
                warnings.append(f"No {source_field} document was discovered.")
            continue
        title = str(title_value or "Untitled document")
        override = overrides.get(source_field, {}) if isinstance(overrides, dict) else {}
        kind = str(override.get("kind") or _document_kind(title, source_field))
        status = str(override.get("status") or _document_status(title))
        if source_field == "agenda" and kind == "minutes":
            warnings.append("The portal agenda field contains a minutes document; retained by content type.")
        if source_field == "minutes" and kind != "minutes":
            warnings.append("The portal minutes field does not appear to contain minutes.")
        document = {
            "kind": kind,
            "status": status,
            "title": title,
            "url": str(url_value),
            "published_at": override.get("published_at"),
            "content_hash": override.get("content_hash"),
            "source_field": source_field,
        }
        inspection = override.get("pdf_inspection")
        if isinstance(inspection, dict):
            document["pdf_inspection"] = {key: value for key, value in inspection.items() if key != "linked_documents"}
        result.append(document)
        seen_urls.add(str(url_value))
        if isinstance(inspection, dict):
            for linked in inspection.get("linked_documents", []):
                if not isinstance(linked, dict) or not linked.get("url"):
                    continue
                linked_url = str(linked["url"])
                if linked_url in seen_urls:
                    continue
                result.append(
                    {
                        "kind": str(linked.get("kind", "other")),
                        "status": str(linked.get("status", "unknown")),
                        "title": str(linked.get("title") or "Linked document"),
                        "url": linked_url,
                        "published_at": None,
                        "content_hash": None,
                        "source_field": f"{source_field}_link",
                    }
                )
                seen_urls.add(linked_url)
        elif source_field == "agenda" and kind in {"agenda", "agenda_package"}:
            warnings.append("Agenda PDF links were not inspected; linked reports and attachments are unknown.")
        if override.get("inspection_error"):
            warnings.append(f"{source_field.capitalize()} PDF inspection failed: {override['inspection_error']}")
    return result


def _video(raw: dict[str, Any], evidence: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    direct_url = raw.get("crf6e_meetinglink")
    candidate = evidence.get("video", {}) if isinstance(evidence.get("video", {}), dict) else {}
    candidate_url = candidate.get("url")
    url = str(direct_url or candidate_url) if (direct_url or candidate_url) else None
    youtube_id = _youtube_id(url)
    reasons: list[str] = []
    if direct_url:
        confidence = 1.0
        reasons.append("Official meeting record links directly to this video.")
        if candidate_url and _youtube_id(str(candidate_url)) == youtube_id:
            reasons.append("Independent official-channel evidence identifies the same YouTube video.")
    elif candidate_url:
        try:
            confidence = float(candidate.get("match_confidence", 0.0))
        except (TypeError, ValueError) as exc:
            raise DiscoveryError("Video match confidence must be numeric") from exc
        reasons.extend(str(reason) for reason in candidate.get("match_reasons", []))
        warnings.append("The portal has no video link; candidate match requires independent evidence.")
    else:
        confidence = 0.0
        warnings.append("No meeting video was discovered.")
    availability = str(candidate.get("availability", "unknown"))
    transcript_status = str(candidate.get("transcript_status", "unknown"))
    if transcript_status not in {"available", "delayed", "unavailable", "unknown"}:
        raise DiscoveryError(f"Invalid transcript status: {transcript_status}")
    if url and not youtube_id:
        warnings.append("Video URL is not a recognized YouTube URL.")
    if availability == "unavailable":
        warnings.append("Matched video is unavailable.")
    if transcript_status in {"unavailable", "delayed"}:
        warnings.append(f"Transcript is {transcript_status}.")
    if url and confidence < 0.8:
        warnings.append("Video match confidence is below 0.80; manual review required.")
    return {
        "url": url,
        "youtube_id": youtube_id,
        "match_confidence": confidence,
        "match_reasons": reasons,
        "availability": availability,
        "transcript_status": transcript_status,
        "caption_kind": candidate.get("caption_kind"),
        "shared_with_source_ids": candidate.get("shared_with_source_ids", []),
    }


def normalize_meeting(
    raw: dict[str, Any], evidence: dict[str, Any] | None = None, discovered_at: str | None = None
) -> dict[str, Any]:
    evidence = evidence or {}
    source_id = raw.get("crf6e_cityconnectionsmeetingsid")
    title = str(raw.get("crf6e_title") or raw.get("crf6e_meetingtype") or "Untitled meeting")
    scheduled_start = raw.get("crf6e_meetingdate")
    warnings: list[str] = []
    scheduled_date: date | None = None
    if isinstance(scheduled_start, str):
        try:
            scheduled = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            scheduled_date = scheduled.astimezone(AJAX_TIMEZONE).date()
        except ValueError:
            warnings.append("Scheduled start is not valid ISO-8601.")
    embedded_date = _title_date(title)
    if embedded_date and scheduled_date and embedded_date != scheduled_date:
        warnings.append("Meeting title date conflicts with the scheduled date.")
    if not source_id:
        warnings.append("Official source ID is absent; using a deterministic synthetic local identity.")
    official_page_url = (
        f"{API_ROOT}/{ENTITY_SET}({source_id})" if source_id else str(raw.get("official_page_url") or "")
    )
    record = {
        "local_id": _local_id(source_id, title, scheduled_start),
        "source_meeting_id": source_id,
        "title": title,
        "normalized_type": _normalized_type(raw.get("crf6e_meetingtype")),
        "scheduled_start": scheduled_start,
        "status": _normalized_status(raw.get("crf6e_meetingstatus")),
        "official_page_url": official_page_url,
        "source_modified_at": raw.get("modifiedon"),
        "documents": _documents(raw, evidence, warnings),
        "video": _video(raw, evidence, warnings),
        "discovered_at": discovered_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "warnings": warnings,
    }
    return record


def _in_range(raw: dict[str, Any], start: date, end: date) -> bool:
    value = raw.get("crf6e_meetingdate")
    if not isinstance(value, str):
        return False
    try:
        meeting_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if meeting_datetime.tzinfo is None:
            meeting_datetime = meeting_datetime.replace(tzinfo=timezone.utc)
        meeting_date = meeting_datetime.astimezone(AJAX_TIMEZONE).date()
    except ValueError:
        return False
    return start <= meeting_date <= end


def discover(
    records: Iterable[dict[str, Any]],
    start: date,
    end: date,
    evidence_index: dict[str, Any] | None = None,
    discovered_at: str | None = None,
) -> dict[str, Any]:
    if start > end:
        raise DiscoveryError("Start date must not be after end date")
    evidence_meetings = (evidence_index or {}).get("meetings", {})
    normalized: dict[str, dict[str, Any]] = {}
    for raw in records:
        if not _in_range(raw, start, end):
            continue
        source_id = str(raw.get("crf6e_cityconnectionsmeetingsid") or "")
        evidence = evidence_meetings.get(source_id, {}) if isinstance(evidence_meetings, dict) else {}
        meeting = normalize_meeting(raw, evidence=evidence, discovered_at=discovered_at)
        if meeting["local_id"] in normalized:
            meeting["warnings"].append("Duplicate source record replaced during idempotent normalization.")
        normalized[meeting["local_id"]] = meeting
    meetings = sorted(normalized.values(), key=lambda item: (item.get("scheduled_start") or "", item["local_id"]))
    return {
        "schema_version": "0.1",
        "query": {"start": start.isoformat(), "end": end.isoformat()},
        "meeting_count": len(meetings),
        "meetings": meetings,
    }
