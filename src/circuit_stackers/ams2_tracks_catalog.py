"""Collect AMS2 track/layout metadata from the public Wiki."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

from .paths import resource_path, user_data_dir


WIKI_TRACKS_URL = "https://automobilista2.wiki.gg/wiki/Tracks_and_Layouts"
TRACK_CACHE_PATH = user_data_dir() / "ams2_tracks_cache.json"


@dataclass(frozen=True)
class TrackMatch:
    wiki_track: str
    layout: str
    local_track: str = ""
    local_layout: str = ""
    candidates: tuple[str, ...] = ()


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unescape(value).casefold())


def fetch_tracks_html(timeout: float = 15.0) -> str:
    request = Request(WIKI_TRACKS_URL, headers={"User-Agent": "CircuitStackers AMS2 metadata updater"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _table_rows(html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
        cells = []
        for raw_cell in re.findall(r"<(?:th|td)\b[^>]*>(.*?)</(?:th|td)>", raw_row, re.IGNORECASE | re.DOTALL):
            value = re.sub(r"<[^>]+>", " ", raw_cell)
            cells.append(" ".join(unescape(value).split()))
        if cells:
            rows.append(cells)
    return rows


def parse_wiki_tracks(html: str) -> list[dict[str, str]]:
    """Parse the Wiki's full layout table into normalized layout records."""
    for rows in [_table_rows(html)]:
        header_index = next(
            (i for i, row in enumerate(rows) if "layout" in {cell.casefold() for cell in row}),
            None,
        )
        if header_index is None:
            continue
        header = [cell.casefold() for cell in rows[header_index]]
        track_index = next((i for i, cell in enumerate(header) if cell == "track"), None)
        layout_index = next((i for i, cell in enumerate(header) if cell == "layout"), None)
        if track_index is None or layout_index is None:
            continue
        records: list[dict[str, str]] = []
        for row in rows[header_index + 1 :]:
            if len(row) <= max(track_index, layout_index):
                continue
            track = row[track_index].strip()
            layout = row[layout_index].strip()
            if track and layout:
                records.append({"track": track, "layout": layout})
        if records:
            return records
    return []


def _local_ams2_tracks() -> list[dict[str, str]]:
    path = resource_path("data", "Tracks.csv")
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [row for row in csv.DictReader(handle) if str(row.get("Game", "")).casefold() == "ams2"]
    except (OSError, csv.Error):
        return []


def scan_packed_tracks(install_root: Path | None) -> list[str]:
    if install_root is None:
        return []
    roots = [install_root / "Pakfiles" / "Tracks", install_root / "Pakfiles" / "TracksAndLayouts"]
    files = [path for root in roots if root.exists() for path in root.rglob("*.bff")]
    return sorted({path.stem.removesuffix("_Track") for path in files}, key=str.casefold)


def match_tracks(records: list[dict[str, str]], local: list[dict[str, str]]) -> list[TrackMatch]:
    local_pairs = [(str(row.get("Track", "")).strip(), str(row.get("Layout", "")).strip()) for row in local]
    result: list[TrackMatch] = []
    for record in records:
        track, layout = record["track"], record["layout"]
        exact = next((pair for pair in local_pairs if _compact(pair[0]) == _compact(track) and _compact(pair[1]) == _compact(layout)), None)
        if exact:
            result.append(TrackMatch(track, layout, exact[0], exact[1]))
            continue
        candidates = tuple(f"{track_name} | {layout_name}" for track_name, layout_name in local_pairs if _compact(track_name) == _compact(track))[:3]
        result.append(TrackMatch(track, layout, candidates=candidates))
    return result


def update_track_metadata(output_dir: Path, install_root: Path | None = None) -> tuple[Path, str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "ams2_tracks_report.json"
    metadata_path = output_dir / "ams2_tracks_metadata.json"
    source = "unavailable"
    failed = 0
    try:
        records = parse_wiki_tracks(fetch_tracks_html())
        if not records:
            raise ValueError("Wiki page contained no parseable track table")
        source = "wiki-live"
        TRACK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TRACK_CACHE_PATH.write_text(json.dumps({"source": WIKI_TRACKS_URL, "tracks": records}, indent=2), encoding="utf-8")
    except (OSError, ValueError, TimeoutError):
        try:
            cached = json.loads(TRACK_CACHE_PATH.read_text(encoding="utf-8"))
            records = cached.get("tracks", [])
            source = str(cached.get("source", "cache")) if records else "unavailable"
        except (OSError, json.JSONDecodeError):
            records = []
        if not records:
            records = [
                {"track": str(row.get("Track", "")).strip(), "layout": str(row.get("Layout", "")).strip()}
                for row in _local_ams2_tracks()
                if str(row.get("Track", "")).strip() and str(row.get("Layout", "")).strip()
            ]
            source = "local-csv" if records else "unavailable"
        failed = 1
    local = _local_ams2_tracks()
    packed_tracks = scan_packed_tracks(install_root)
    matches = match_tracks(records, local)
    report = {"source": WIKI_TRACKS_URL, "catalog_source": source, "records": records, "matches": [asdict(item) for item in matches], "matched_count": sum(bool(item.local_track) for item in matches), "unmatched_count": sum(not item.local_track for item in matches), "installed_track_packages": packed_tracks, "failed_pages": failed}
    metadata = {"schema_version": 1, "source": WIKI_TRACKS_URL, "tracks": records, "installed_track_packages": packed_tracks}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return report_path, source, failed
