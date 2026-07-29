"""Download helpers for biblical place raw sources."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


OPENBIBLE_FILES = {
    "license.txt": "https://raw.githubusercontent.com/openbibleinfo/Bible-Geocoding-Data/main/license.txt",
    "readme.md": "https://raw.githubusercontent.com/openbibleinfo/Bible-Geocoding-Data/main/readme.md",
    "ancient.jsonl": "https://raw.githubusercontent.com/openbibleinfo/Bible-Geocoding-Data/main/data/ancient.jsonl",
    "modern.jsonl": "https://raw.githubusercontent.com/openbibleinfo/Bible-Geocoding-Data/main/data/modern.jsonl",
}


@dataclass
class DownloadReport:
    downloaded: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "downloaded": self.downloaded,
            "skipped_existing": self.skipped_existing,
            "failed": self.failed,
            "blocked": self.blocked,
        }


def _fetch(url: str, dest: Path, *, force: bool, report: DownloadReport) -> None:
    label = str(dest)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        report.skipped_existing.append(label)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "textus-map-import/1.0", "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            dest.write_bytes(response.read())
        report.downloaded.append(label)
    except urllib.error.URLError as exc:
        report.failed.append(f"{label}: {exc}")
        report.blocked.append(url)
    except Exception as exc:  # pragma: no cover - network variability
        report.failed.append(f"{label}: {exc}")
        report.blocked.append(url)


def download_openbible(raw_dir: Path, *, force: bool = False) -> DownloadReport:
    report = DownloadReport()
    target = raw_dir / "openbible"
    for name, url in OPENBIBLE_FILES.items():
        _fetch(url, target / name, force=force, report=report)
    return report


def download_pleiades_ids(
    raw_dir: Path,
    pleiades_ids: list[str],
    *,
    force: bool = False,
) -> DownloadReport:
    report = DownloadReport()
    target = raw_dir / "pleiades"
    for pid in sorted(set(pleiades_ids)):
        if not pid:
            continue
        url = f"https://pleiades.stoa.org/places/{pid}/json"
        _fetch(url, target / f"{pid}.json", force=force, report=report)
    return report


def write_download_manifest(path: Path, reports: dict[str, DownloadReport]) -> None:
    payload = {name: report.as_dict() for name, report in reports.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
