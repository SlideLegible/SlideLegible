"""In-memory registry plus a private temporary folder for one local server process.

Everything is deleted when the server shuts down (retention policy for the
local single-user deployment).
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from slidelegible.api import AnalysisResult, CorrectionResult


def new_id() -> str:
    return secrets.token_urlsafe(12)


@dataclass
class Upload:
    id: str
    filename: str
    path: Path
    slides: int


@dataclass
class Artifact:
    id: str
    path: Path
    media_type: str
    download_name: str | None = None


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | completed | failed
    stage: str = "queued"
    progress: float = 0.0
    error: dict[str, str] | None = None
    result: dict[str, Any] | None = None


@dataclass
class AnalysisRecord:
    id: str
    upload_id: str
    result: AnalysisResult
    original_previews: dict[int, str] = field(default_factory=dict)  # slide -> artifact id
    proposed: CorrectionRecord | None = None


@dataclass
class CorrectionRecord:
    id: str
    analysis_id: str
    result: CorrectionResult
    pptx_artifact: str
    previews: dict[int, str] = field(default_factory=dict)
    render_error: str | None = None


class Store:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="slidelegible-web-"))
        self.lock = threading.Lock()
        self.uploads: dict[str, Upload] = {}
        self.artifacts: dict[str, Artifact] = {}
        self.jobs: dict[str, Job] = {}
        self.analyses: dict[str, AnalysisRecord] = {}
        self.corrections: dict[str, CorrectionRecord] = {}

    def write_artifact(
        self, data: bytes, suffix: str, media_type: str, download_name: str | None = None
    ) -> Artifact:
        artifact_id = new_id()
        path = self.root / f"{artifact_id}{suffix}"
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic finalization
        artifact = Artifact(artifact_id, path, media_type, download_name)
        with self.lock:
            self.artifacts[artifact_id] = artifact
        return artifact

    def new_job(self, kind: str) -> Job:
        job = Job(new_id(), kind)
        with self.lock:
            self.jobs[job.id] = job
        return job

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
